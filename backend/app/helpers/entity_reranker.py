from __future__ import annotations

"""Entity reranking and filtering over evidence-backed candidates."""

import math
from dataclasses import dataclass
from typing import Literal
from typing import Protocol

import bm25s

from backend.app.contracts import EvidenceChunk, EvidenceStore, ExtractorLightOutput, PlannerOutput
from backend.app.helpers.chunk_retrieval_preprocessor import (
    ChunkRetrievalPreprocessor,
    DefaultChunkRetrievalPreprocessor,
)
from backend.app.helpers.ranking_utils import dense_normalized_scores


UNIQUE_SOURCE_COUNT_WEIGHT = 0.30
QUERY_VARIANT_COVERAGE_WEIGHT = 0.20
BEST_SOURCE_QUALITY_WEIGHT = 0.20
AVG_SELECTED_CHUNK_RANK_WEIGHT = 0.10
DEDUPED_UNIQUE_CHUNK_COUNT_WEIGHT = 0.10
ANTI_SOURCE_CONCENTRATION_WEIGHT = 0.10

QUERY_ALIGNMENT_BM25_WEIGHT = 0.60
QUERY_ALIGNMENT_SPAN_WEIGHT = 0.20
QUERY_ALIGNMENT_ANCHOR_WEIGHT = 0.20

ENTITY_QUERY_ALIGNMENT_BETA = 0.50
MIN_FINAL_ENTITY_SCORE = 0.30
ENTITY_SELECTION_MMR_LAMBDA = 0.75

UNIQUE_SOURCE_COUNT_NORMALIZER = 3
DEDUPED_CHUNK_COUNT_NORMALIZER = 4
NEAR_DUPLICATE_OVERLAP_THRESHOLD = 0.85


class EntityReranker(Protocol):
    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
    ) -> "EntityRankingResult":
        """Rank evidence-backed candidates before extractor construction."""


@dataclass(frozen=True)
class EntityRankingFeatures:
    unique_source_count: int
    deduped_unique_chunk_count: int
    query_variant_coverage_count: int
    best_source_quality_score: float
    avg_selected_chunk_rank_score: float
    source_concentration_ratio: float


@dataclass(frozen=True)
class RankedEntity:
    entity_name: str
    candidate_type: Literal["core", "discovery"]
    supporting_query_variants: list[str]
    dominant_query_variant: str | None
    support_score: float
    query_alignment_score: float
    final_score: float
    features: EntityRankingFeatures


@dataclass(frozen=True)
class EntityRankingResult:
    kept_entities: list[RankedEntity]
    filtered_entities: list[RankedEntity]

    @property
    def ranked_entities(self) -> list[RankedEntity]:
        return self.kept_entities

    @property
    def ranked_entity_names(self) -> list[str]:
        return [entity.entity_name for entity in self.kept_entities]


class DefaultEntityReranker:
    def __init__(
        self,
        *,
        preprocessor: ChunkRetrievalPreprocessor | None = None,
        min_final_entity_score: float = MIN_FINAL_ENTITY_SCORE,
    ) -> None:
        self._preprocessor = preprocessor or DefaultChunkRetrievalPreprocessor()
        self._min_final_entity_score = max(0.0, min_final_entity_score)

    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
    ) -> EntityRankingResult:
        candidate_names = [
            candidate_name
            for candidate_name in extractor_light_output.candidate_names
            if evidence_store.chunks_by_entity.get(candidate_name)
        ]
        if not candidate_names:
            return EntityRankingResult(kept_entities=[], filtered_entities=[])

        deduped_chunks_by_entity = {
            candidate_name: _deduped_chunks(
                chunks=evidence_store.chunks_by_entity.get(candidate_name, []),
                preprocessor=self._preprocessor,
            )
            for candidate_name in candidate_names
        }
        total_query_variant_count = _total_query_variant_count(planner_output)
        preferred_query_variants = _preferred_query_variants(planner_output)
        features_by_entity = {
            candidate_name: _entity_features(
                chunks=deduped_chunks_by_entity[candidate_name],
                total_query_variant_count=total_query_variant_count,
            )
            for candidate_name in candidate_names
        }
        query_variant_counts_by_entity = {
            candidate_name: _query_variant_counts(deduped_chunks_by_entity[candidate_name])
            for candidate_name in candidate_names
        }
        query_alignment_scores = _query_alignment_scores(
            planner_output=planner_output,
            deduped_chunks_by_entity=deduped_chunks_by_entity,
            preprocessor=self._preprocessor,
        )

        ranked_entities = [
            RankedEntity(
                entity_name=candidate_name,
                candidate_type=_candidate_type(query_alignment_scores.get(candidate_name, 0.0)),
                supporting_query_variants=_supporting_query_variants(
                    query_variant_counts_by_entity[candidate_name],
                    preferred_query_variants=preferred_query_variants,
                ),
                dominant_query_variant=_dominant_query_variant(
                    query_variant_counts_by_entity[candidate_name],
                    preferred_query_variants=preferred_query_variants,
                ),
                support_score=_support_score(
                    features_by_entity[candidate_name],
                    total_query_variant_count=total_query_variant_count,
                ),
                query_alignment_score=query_alignment_scores.get(candidate_name, 0.0),
                final_score=0.0,
                features=features_by_entity[candidate_name],
            )
            for candidate_name in candidate_names
        ]
        ranked_entities = [
            RankedEntity(
                entity_name=entity.entity_name,
                candidate_type=entity.candidate_type,
                supporting_query_variants=entity.supporting_query_variants,
                dominant_query_variant=entity.dominant_query_variant,
                support_score=entity.support_score,
                query_alignment_score=entity.query_alignment_score,
                final_score=((1.0 - ENTITY_QUERY_ALIGNMENT_BETA) * entity.support_score)
                + (ENTITY_QUERY_ALIGNMENT_BETA * entity.query_alignment_score),
                features=entity.features,
            )
            for entity in ranked_entities
        ]
        ranked_entities.sort(
            key=lambda entity: (-entity.final_score, -entity.support_score, -entity.query_alignment_score, entity.entity_name.casefold())
        )

        eligible_entities = [
            entity
            for entity in ranked_entities
            if entity.final_score >= self._min_final_entity_score
        ]
        if not eligible_entities:
            return EntityRankingResult(kept_entities=ranked_entities, filtered_entities=[])
        kept_entities = _select_diverse_entities(eligible_entities)
        kept_entity_names = {entity.entity_name for entity in kept_entities}
        filtered_entities = [entity for entity in ranked_entities if entity.entity_name not in kept_entity_names]
        return EntityRankingResult(kept_entities=kept_entities, filtered_entities=filtered_entities)


def _entity_features(
    *,
    chunks: list[EvidenceChunk],
    total_query_variant_count: int,
) -> EntityRankingFeatures:
    unique_sources = {str(chunk.source_url) for chunk in chunks}
    query_variants = {
        query_source
        for chunk in chunks
        for query_source in chunk.query_sources
    }
    source_counts: dict[str, int] = {}
    for chunk in chunks:
        source_url = str(chunk.source_url)
        source_counts[source_url] = source_counts.get(source_url, 0) + 1

    return EntityRankingFeatures(
        unique_source_count=len(unique_sources),
        deduped_unique_chunk_count=len(chunks),
        query_variant_coverage_count=min(len(query_variants), total_query_variant_count),
        best_source_quality_score=max((_source_quality_score(chunk) for chunk in chunks), default=0.0),
        avg_selected_chunk_rank_score=_avg_selected_chunk_rank_score(chunks),
        source_concentration_ratio=(
            max(source_counts.values()) / len(chunks)
            if chunks and source_counts
            else 1.0
        ),
    )


def _support_score(
    features: EntityRankingFeatures,
    *,
    total_query_variant_count: int,
) -> float:
    unique_source_score = min(features.unique_source_count / UNIQUE_SOURCE_COUNT_NORMALIZER, 1.0)
    deduped_chunk_score = min(features.deduped_unique_chunk_count / DEDUPED_CHUNK_COUNT_NORMALIZER, 1.0)
    query_variant_coverage_score = min(
        features.query_variant_coverage_count / max(total_query_variant_count, 1),
        1.0,
    )
    anti_concentration_score = max(0.0, 1.0 - features.source_concentration_ratio)
    return (
        UNIQUE_SOURCE_COUNT_WEIGHT * unique_source_score
        + QUERY_VARIANT_COVERAGE_WEIGHT * query_variant_coverage_score
        + BEST_SOURCE_QUALITY_WEIGHT * features.best_source_quality_score
        + AVG_SELECTED_CHUNK_RANK_WEIGHT * features.avg_selected_chunk_rank_score
        + DEDUPED_UNIQUE_CHUNK_COUNT_WEIGHT * deduped_chunk_score
        + ANTI_SOURCE_CONCENTRATION_WEIGHT * anti_concentration_score
    )


def _query_alignment_scores(
    *,
    planner_output: PlannerOutput,
    deduped_chunks_by_entity: dict[str, list[EvidenceChunk]],
    preprocessor: ChunkRetrievalPreprocessor,
) -> dict[str, float]:
    entity_names = list(deduped_chunks_by_entity.keys())
    if not entity_names:
        return {}

    evidence_tokens_by_entity = {
        entity_name: preprocessor.preprocess_text(" ".join(chunk.text for chunk in chunks))
        for entity_name, chunks in deduped_chunks_by_entity.items()
    }

    retriever = bm25s.BM25()
    corpus_tokens = [evidence_tokens_by_entity[entity_name] for entity_name in entity_names]
    retriever.index(corpus_tokens)

    normalized_query_tokens = preprocessor.preprocess_text(planner_output.normalized_query)
    results, scores = retriever.retrieve([normalized_query_tokens], k=len(entity_names), show_progress=False)
    bm25_scores = dense_normalized_scores(
        result_ids=results[0].tolist(),
        result_scores=scores[0].tolist(),
        corpus_size=len(entity_names),
    )
    anchor_terms = _anchor_terms(planner_output, preprocessor)

    return {
        entity_name: (
            QUERY_ALIGNMENT_BM25_WEIGHT * bm25_scores[index]
            + QUERY_ALIGNMENT_SPAN_WEIGHT * _max_query_span_score(normalized_query_tokens, evidence_tokens_by_entity[entity_name])
            + QUERY_ALIGNMENT_ANCHOR_WEIGHT * _anchor_coverage_score(anchor_terms, evidence_tokens_by_entity[entity_name])
        )
        for index, entity_name in enumerate(entity_names)
    }


def _candidate_type(query_alignment_score: float) -> Literal["core", "discovery"]:
    return "core" if query_alignment_score >= 0.5 else "discovery"


def _preferred_query_variants(planner_output: PlannerOutput) -> list[str]:
    ordered_variants = [
        planner_output.normalized_query,
        planner_output.base_query,
        *planner_output.initial_query_rewrites,
    ]
    seen: set[str] = set()
    preferred: list[str] = []
    for query_variant in ordered_variants:
        normalized_variant = query_variant.strip()
        if not normalized_variant or normalized_variant in seen:
            continue
        seen.add(normalized_variant)
        preferred.append(normalized_variant)
    return preferred


def _query_variant_counts(chunks: list[EvidenceChunk]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        for query_variant in chunk.query_sources:
            normalized_variant = query_variant.strip()
            if not normalized_variant:
                continue
            counts[normalized_variant] = counts.get(normalized_variant, 0) + 1
    return counts


def _supporting_query_variants(
    query_variant_counts: dict[str, int],
    *,
    preferred_query_variants: list[str],
) -> list[str]:
    ordered_variants = [
        query_variant
        for query_variant in preferred_query_variants
        if query_variant_counts.get(query_variant, 0) > 0
    ]
    remaining_variants = sorted(
        (
            query_variant
            for query_variant in query_variant_counts
            if query_variant not in ordered_variants
        ),
        key=lambda query_variant: query_variant.casefold(),
    )
    return [*ordered_variants, *remaining_variants]


def _dominant_query_variant(
    query_variant_counts: dict[str, int],
    *,
    preferred_query_variants: list[str],
) -> str | None:
    if not query_variant_counts:
        return None

    preferred_positions = {
        query_variant: index
        for index, query_variant in enumerate(preferred_query_variants)
    }
    return min(
        query_variant_counts,
        key=lambda query_variant: (
            -query_variant_counts[query_variant],
            preferred_positions.get(query_variant, len(preferred_positions)),
            query_variant.casefold(),
        ),
    )


def _select_diverse_entities(ranked_entities: list[RankedEntity]) -> list[RankedEntity]:
    if len(ranked_entities) <= 1:
        return ranked_entities

    remaining_entities = list(ranked_entities)
    selected_entities: list[RankedEntity] = []

    while remaining_entities:
        if not selected_entities:
            selected_entities.append(remaining_entities.pop(0))
            continue

        next_entity = max(
            remaining_entities,
            key=lambda candidate: _mmr_score(candidate, selected_entities),
        )
        remaining_entities.remove(next_entity)
        selected_entities.append(next_entity)

    return selected_entities


def _mmr_score(candidate: RankedEntity, selected_entities: list[RankedEntity]) -> float:
    redundancy_penalty = max(
        (_query_variant_similarity(candidate, selected_entity) for selected_entity in selected_entities),
        default=0.0,
    )
    return (
        ENTITY_SELECTION_MMR_LAMBDA * candidate.final_score
        - (1.0 - ENTITY_SELECTION_MMR_LAMBDA) * redundancy_penalty
    )


def _query_variant_similarity(left: RankedEntity, right: RankedEntity) -> float:
    if (
        left.dominant_query_variant
        and right.dominant_query_variant
        and left.dominant_query_variant == right.dominant_query_variant
    ):
        return 1.0

    if set(left.supporting_query_variants) & set(right.supporting_query_variants):
        return 0.5

    return 0.0


def _deduped_chunks(
    *,
    chunks: list[EvidenceChunk],
    preprocessor: ChunkRetrievalPreprocessor,
) -> list[EvidenceChunk]:
    deduped_chunks: list[EvidenceChunk] = []
    exact_keys: set[tuple[str, str]] = set()
    tokens_by_source_and_index: list[tuple[str, frozenset[str]]] = []

    for chunk in chunks:
        normalized_tokens = preprocessor.preprocess_text(chunk.text)
        exact_key = (str(chunk.source_url), " ".join(normalized_tokens))
        if exact_key in exact_keys:
            continue

        normalized_token_set = frozenset(normalized_tokens)
        source_url = str(chunk.source_url)
        if normalized_token_set and any(
            existing_source_url == source_url
            and _token_overlap_ratio(normalized_token_set, existing_token_set) >= NEAR_DUPLICATE_OVERLAP_THRESHOLD
            for existing_source_url, existing_token_set in tokens_by_source_and_index
        ):
            continue

        exact_keys.add(exact_key)
        tokens_by_source_and_index.append((source_url, normalized_token_set))
        deduped_chunks.append(chunk)

    return deduped_chunks


def _total_query_variant_count(planner_output: PlannerOutput) -> int:
    query_variants = [planner_output.base_query, *planner_output.initial_query_rewrites]
    return max(1, len({query for query in query_variants if query.strip()}))


def _source_quality_score(chunk: EvidenceChunk) -> float:
    if chunk.source_quality.value == "high" and chunk.officiality.value != "low_quality":
        return 1.0
    if chunk.source_quality.value == "medium" and chunk.officiality.value != "low_quality":
        return 0.5
    return 0.0


def _avg_selected_chunk_rank_score(chunks: list[EvidenceChunk]) -> float:
    rank_scores = [
        1.0 / math.sqrt(chunk.selected_chunk_rank)
        for chunk in chunks
        if chunk.selected_chunk_rank is not None
    ]
    if not rank_scores:
        return 0.0
    return sum(rank_scores) / len(rank_scores)
def _anchor_terms(
    planner_output: PlannerOutput,
    preprocessor: ChunkRetrievalPreprocessor,
) -> set[str]:
    query_texts = [
        planner_output.normalized_query,
        planner_output.base_query,
        *planner_output.initial_query_rewrites,
    ]
    token_sets = [
        set(preprocessor.preprocess_text(query_text))
        for query_text in query_texts
        if query_text.strip()
    ]
    if not token_sets:
        return set()
    intersection = set.intersection(*token_sets)
    return intersection or token_sets[0]


def _max_query_span_score(query_tokens: list[str], evidence_tokens: list[str]) -> float:
    if not query_tokens or not evidence_tokens:
        return 0.0
    best_span = 0
    query_length = len(query_tokens)
    for start in range(query_length):
        for end in range(start + 1, query_length + 1):
            span = query_tokens[start:end]
            if len(span) <= best_span:
                continue
            if _contains_subsequence(evidence_tokens, span):
                best_span = len(span)
    return best_span / query_length


def _contains_subsequence(tokens: list[str], subsequence: list[str]) -> bool:
    if not subsequence or len(subsequence) > len(tokens):
        return False
    subsequence_length = len(subsequence)
    return any(
        tokens[index : index + subsequence_length] == subsequence
        for index in range(len(tokens) - subsequence_length + 1)
    )


def _anchor_coverage_score(anchor_terms: set[str], evidence_tokens: list[str]) -> float:
    if not anchor_terms:
        return 0.0
    evidence_token_set = set(evidence_tokens)
    return len(anchor_terms & evidence_token_set) / len(anchor_terms)


def _token_overlap_ratio(left_tokens: frozenset[str], right_tokens: frozenset[str]) -> float:
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))
