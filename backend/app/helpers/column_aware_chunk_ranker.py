from __future__ import annotations

from dataclasses import dataclass

import bm25s

from backend.app.contracts import ExtractedEntity, UrlSource
from backend.app.helpers.chunk_retrieval_preprocessor import (
    ChunkRetrievalPreprocessor,
    DefaultChunkRetrievalPreprocessor,
)
from backend.app.helpers.column_facet_generator import ColumnFacetOutput
from backend.app.helpers.ranking_utils import dense_normalized_scores


ENTITY_PRESENCE_WEIGHT = 0.20
COLUMN_MATCH_WEIGHT = 0.50
BASE_QUERY_MATCH_WEIGHT = 0.20
CROSS_ENTITY_CLEANLINESS_WEIGHT = 0.10

MAX_SELECTED_CHUNKS_PER_PAIR = 3
REUSED_SOURCE_SCORE_RATIO_THRESHOLD = 0.90


@dataclass(frozen=True)
class RankedColumnChunk:
    entity_name: str
    column: str
    chunk_id: str
    source_id: str
    score: float
    rank: int


@dataclass(frozen=True)
class ColumnAwareChunkRankingOutput:
    url_sources: list[UrlSource]
    ranked_chunks: list[RankedColumnChunk]

    def top_chunks_for(self, *, entity_name: str, column: str) -> list[RankedColumnChunk]:
        return [
            ranked_chunk
            for ranked_chunk in self.ranked_chunks
            if ranked_chunk.entity_name == entity_name and ranked_chunk.column == column
        ]


class DefaultColumnAwareChunkRanker:
    def __init__(
        self,
        *,
        preprocessor: ChunkRetrievalPreprocessor | None = None,
    ) -> None:
        self._preprocessor = preprocessor or DefaultChunkRetrievalPreprocessor()

    def run(
        self,
        *,
        normalized_query: str,
        extracted_entities: list[ExtractedEntity],
        sparse_columns: list[str],
        facet_output: ColumnFacetOutput,
        url_sources: list[UrlSource],
    ) -> ColumnAwareChunkRankingOutput:
        if not extracted_entities or not sparse_columns or not url_sources:
            return ColumnAwareChunkRankingOutput(url_sources=url_sources, ranked_chunks=[])

        candidate_names = [entity.entity_name for entity in extracted_entities]
        chunk_records = [
            _ChunkRecord(
                chunk_id=chunk.chunk_id,
                source_id=chunk.source_id,
                tokens=self._preprocessor.preprocess_text(chunk.text),
            )
            for source in url_sources
            for chunk in source.chunks
            if chunk.text.strip()
        ]
        if not chunk_records:
            return ColumnAwareChunkRankingOutput(url_sources=url_sources, ranked_chunks=[])

        query_tokens = self._preprocessor.preprocess_text(normalized_query)
        bm25_scores = _query_bm25_scores(chunk_records=chunk_records, query_tokens=query_tokens)
        query_anchor_terms = set(query_tokens)
        entity_tokens_by_name = {
            entity_name: self._preprocessor.preprocess_text(entity_name)
            for entity_name in candidate_names
        }
        facet_terms_by_column = {
            facet.column: [self._preprocessor.preprocess_text(term) for term in facet.facet_terms if term.strip()]
            for facet in facet_output.facets
            if facet.column in sparse_columns
        }

        ranked_chunks: list[RankedColumnChunk] = []
        for entity_name in candidate_names:
            target_entity_tokens = entity_tokens_by_name.get(entity_name, [])
            for column in sparse_columns:
                facet_term_tokens = facet_terms_by_column.get(column, [])
                column_rankings = [
                    (
                        chunk_record,
                        _final_score(
                            target_entity_tokens=target_entity_tokens,
                            all_entity_tokens_by_name=entity_tokens_by_name,
                            query_tokens=query_tokens,
                            query_anchor_terms=query_anchor_terms,
                            facet_term_tokens=facet_term_tokens,
                            chunk_tokens=chunk_record.tokens,
                            query_bm25_score=bm25_scores[index],
                        ),
                    )
                    for index, chunk_record in enumerate(chunk_records)
                ]
                positive_rankings = [
                    (chunk_record, score)
                    for chunk_record, score in column_rankings
                    if score > 0.0
                ]
                positive_rankings.sort(
                    key=lambda item: (-item[1], item[0].chunk_id)
                )
                selected_rankings = _select_diverse_rankings(positive_rankings)
                ranked_chunks.extend(
                    RankedColumnChunk(
                        entity_name=entity_name,
                        column=column,
                        chunk_id=chunk_record.chunk_id,
                        source_id=chunk_record.source_id,
                        score=score,
                        rank=rank,
                    )
                    for rank, (chunk_record, score) in enumerate(
                        selected_rankings,
                        start=1,
                    )
                )

        return ColumnAwareChunkRankingOutput(url_sources=url_sources, ranked_chunks=ranked_chunks)


@dataclass(frozen=True)
class _ChunkRecord:
    chunk_id: str
    source_id: str
    tokens: list[str]


def _query_bm25_scores(
    *,
    chunk_records: list[_ChunkRecord],
    query_tokens: list[str],
) -> list[float]:
    if not chunk_records or not query_tokens:
        return [0.0] * len(chunk_records)

    retriever = bm25s.BM25()
    corpus_tokens = [record.tokens for record in chunk_records]
    retriever.index(corpus_tokens)
    results, scores = retriever.retrieve([query_tokens], k=len(chunk_records), show_progress=False)
    return dense_normalized_scores(
        result_ids=results[0].tolist(),
        result_scores=scores[0].tolist(),
        corpus_size=len(chunk_records),
    )


def _final_score(
    *,
    target_entity_tokens: list[str],
    all_entity_tokens_by_name: dict[str, list[str]],
    query_tokens: list[str],
    query_anchor_terms: set[str],
    facet_term_tokens: list[list[str]],
    chunk_tokens: list[str],
    query_bm25_score: float,
) -> float:
    entity_presence_score = _entity_presence_score(target_entity_tokens, chunk_tokens)
    if entity_presence_score <= 0.0:
        return 0.0

    column_match_score = _column_match_score(facet_term_tokens, chunk_tokens)
    base_query_match_score = _base_query_match_score(
        query_tokens=query_tokens,
        query_anchor_terms=query_anchor_terms,
        chunk_tokens=chunk_tokens,
        query_bm25_score=query_bm25_score,
    )
    cross_entity_cleanliness_score = _cross_entity_cleanliness_score(
        target_entity_tokens=target_entity_tokens,
        all_entity_tokens_by_name=all_entity_tokens_by_name,
        chunk_tokens=chunk_tokens,
    )

    return (
        ENTITY_PRESENCE_WEIGHT * entity_presence_score
        + COLUMN_MATCH_WEIGHT * column_match_score
        + BASE_QUERY_MATCH_WEIGHT * base_query_match_score
        + CROSS_ENTITY_CLEANLINESS_WEIGHT * cross_entity_cleanliness_score
    )


def _entity_presence_score(target_entity_tokens: list[str], chunk_tokens: list[str]) -> float:
    if not target_entity_tokens:
        return 0.0
    mention_count = _subsequence_occurrence_count(chunk_tokens, target_entity_tokens)
    if mention_count <= 0:
        return 0.0
    if mention_count == 1:
        return 0.85
    return 1.0


def _column_match_score(facet_term_tokens: list[list[str]], chunk_tokens: list[str]) -> float:
    if not facet_term_tokens or not chunk_tokens:
        return 0.0

    facet_token_set = {
        token
        for facet_tokens in facet_term_tokens
        for token in facet_tokens
    }
    if not facet_token_set:
        return 0.0

    chunk_token_set = set(chunk_tokens)
    overlap_score = len(facet_token_set & chunk_token_set) / len(facet_token_set)
    span_score = max(
        (
            _max_query_span_score(facet_tokens, chunk_tokens)
            for facet_tokens in facet_term_tokens
            if facet_tokens
        ),
        default=0.0,
    )
    return (0.7 * overlap_score) + (0.3 * span_score)


def _base_query_match_score(
    *,
    query_tokens: list[str],
    query_anchor_terms: set[str],
    chunk_tokens: list[str],
    query_bm25_score: float,
) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    span_score = _max_query_span_score(query_tokens, chunk_tokens)
    anchor_score = _anchor_coverage_score(query_anchor_terms, chunk_tokens)
    return (0.6 * query_bm25_score) + (0.2 * span_score) + (0.2 * anchor_score)


def _cross_entity_cleanliness_score(
    *,
    target_entity_tokens: list[str],
    all_entity_tokens_by_name: dict[str, list[str]],
    chunk_tokens: list[str],
) -> float:
    other_entity_mentions = sum(
        1
        for entity_tokens in all_entity_tokens_by_name.values()
        if entity_tokens != target_entity_tokens and _subsequence_occurrence_count(chunk_tokens, entity_tokens) > 0
    )
    if other_entity_mentions <= 0:
        return 1.0
    if other_entity_mentions == 1:
        return 0.4
    return 0.0


def _subsequence_occurrence_count(tokens: list[str], subsequence: list[str]) -> int:
    if not subsequence or len(subsequence) > len(tokens):
        return 0
    subsequence_length = len(subsequence)
    return sum(
        1
        for index in range(len(tokens) - subsequence_length + 1)
        if tokens[index : index + subsequence_length] == subsequence
    )


def _select_diverse_rankings(
    positive_rankings: list[tuple[_ChunkRecord, float]],
) -> list[tuple[_ChunkRecord, float]]:
    selected_rankings: list[tuple[_ChunkRecord, float]] = []
    remaining_rankings = list(positive_rankings)
    seen_source_ids: set[str] = set()

    while remaining_rankings and len(selected_rankings) < MAX_SELECTED_CHUNKS_PER_PAIR:
        best_unseen_index = next(
            (
                index
                for index, (chunk_record, _) in enumerate(remaining_rankings)
                if chunk_record.source_id not in seen_source_ids
            ),
            None,
        )
        if best_unseen_index is None:
            selected_rankings.extend(
                remaining_rankings[: MAX_SELECTED_CHUNKS_PER_PAIR - len(selected_rankings)]
            )
            break

        best_overall_chunk, best_overall_score = remaining_rankings[0]
        best_unseen_chunk, best_unseen_score = remaining_rankings[best_unseen_index]
        if (
            best_overall_chunk.source_id in seen_source_ids
            and best_unseen_score > 0.0
            and best_overall_score < (REUSED_SOURCE_SCORE_RATIO_THRESHOLD * best_unseen_score)
        ):
            chosen_index = best_unseen_index
        else:
            chosen_index = 0

        chosen_chunk, chosen_score = remaining_rankings.pop(chosen_index)
        selected_rankings.append((chosen_chunk, chosen_score))
        seen_source_ids.add(chosen_chunk.source_id)

    return selected_rankings


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
