from __future__ import annotations

"""Request-scoped chunk ranking over retrieved URL sources."""

from dataclasses import dataclass
from typing import Protocol

import bm25s

from backend.app.config import DEFAULT_CHUNK_RANKER_TOP_K
from backend.app.contracts import (
    ChunkScore,
    ChunkRankingOutput,
    PlannerOutput,
    RankedChunk,
    RetrievedChunk,
    UrlSource,
)
from backend.app.helpers.chunk_retrieval_preprocessor import (
    ChunkRetrievalPreprocessor,
    DefaultChunkRetrievalPreprocessor,
)
from backend.app.helpers.ranking_utils import dense_normalized_scores


BASE_QUERY_WEIGHT = 0.45
BEST_REWRITE_WEIGHT = 0.25

REWRITE_SUPPORT_RATIO = 0.80
QUERY_VARIANT_COVERAGE_WEIGHT = 0.10

MAX_QUERY_SPAN_WEIGHT = 0.10
ANCHOR_COVERAGE_WEIGHT = 0.10


class ChunkRanker(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        url_sources: list[UrlSource],
    ) -> ChunkRankingOutput:
        """Rank provider-neutral retrieved chunks for pre-entity retrieval."""


@dataclass(frozen=True)
class QueryBundle:
    base_label: str
    query_text_by_label: dict[str, str]
    rewrite_labels: list[str]
    query_tokens_by_label: dict[str, list[str]]
    anchor_terms: set[str]


class DefaultChunkRanker:
    def __init__(
        self,
        *,
        preprocessor: ChunkRetrievalPreprocessor | None = None,
        top_k: int = DEFAULT_CHUNK_RANKER_TOP_K,
    ) -> None:
        self._preprocessor = preprocessor or DefaultChunkRetrievalPreprocessor()
        self._top_k = max(0, top_k)

    def run(
        self,
        planner_output: PlannerOutput,
        url_sources: list[UrlSource],
    ) -> ChunkRankingOutput:
        chunk_records = [
            _ChunkRecord(
                source=source,
                chunk=chunk,
                retrieval_tokens=self._preprocessor.preprocess_text(chunk.text),
            )
            for source in url_sources
            for chunk in source.chunks
            if chunk.text.strip()
        ]
        if not chunk_records:
            return ChunkRankingOutput(url_sources=url_sources, ranked_chunks=[], selected_chunk_ids=[])

        corpus_tokens = [record.retrieval_tokens for record in chunk_records]
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        queries = _query_bundle(planner_output)
        query_scores = _query_scores(
            retriever=retriever,
            query_bundle=queries,
            preprocessor=self._preprocessor,
            corpus_size=len(chunk_records),
        )

        ranked_chunks = [
            _ranked_chunk(
                planner_output=planner_output,
                record=record,
                query_bundle=queries,
                query_scores=query_scores,
                chunk_index=index,
            )
            for index, record in enumerate(chunk_records)
        ]
        ranked_chunks.sort(key=lambda chunk: (-chunk.score.final_score, chunk.source_id, chunk.chunk_id))
        ranked_chunks = [
            RankedChunk(
                source_id=chunk.source_id,
                chunk_id=chunk.chunk_id,
                rank=index + 1,
                score=chunk.score,
            )
            for index, chunk in enumerate(ranked_chunks)
        ]
        selected_chunk_ids = [chunk.chunk_id for chunk in ranked_chunks[: self._top_k]]
        return ChunkRankingOutput(
            url_sources=url_sources,
            ranked_chunks=ranked_chunks,
            selected_chunk_ids=selected_chunk_ids,
        )

@dataclass(frozen=True)
class _ChunkRecord:
    source: UrlSource
    chunk: RetrievedChunk
    retrieval_tokens: list[str]


def _query_bundle(planner_output: PlannerOutput) -> QueryBundle:
    preprocessor = DefaultChunkRetrievalPreprocessor()
    base_query = planner_output.normalized_query.strip() or planner_output.base_query.strip()
    query_text_by_label = {"base": base_query}
    rewrite_labels: list[str] = []
    for index, rewrite in enumerate(planner_output.initial_query_rewrites, start=1):
        normalized_rewrite = rewrite.strip()
        if not normalized_rewrite or normalized_rewrite == base_query:
            continue
        label = f"rewrite_{index}"
        query_text_by_label[label] = normalized_rewrite
        rewrite_labels.append(label)
    query_tokens_by_label = {
        label: preprocessor.preprocess_text(query_text)
        for label, query_text in query_text_by_label.items()
    }
    return QueryBundle(
        base_label="base",
        query_text_by_label=query_text_by_label,
        rewrite_labels=rewrite_labels,
        query_tokens_by_label=query_tokens_by_label,
        anchor_terms=_anchor_terms(query_tokens_by_label),
    )


def _query_scores(
    *,
    retriever: bm25s.BM25,
    query_bundle: QueryBundle,
    preprocessor: ChunkRetrievalPreprocessor,
    corpus_size: int,
) -> dict[str, list[float]]:
    scores_by_label: dict[str, list[float]] = {}
    for label, query_text in query_bundle.query_text_by_label.items():
        tokenized_query = [preprocessor.preprocess_text(query_text)]
        results, scores = retriever.retrieve(tokenized_query, k=corpus_size, show_progress=False)
        scores_by_label[label] = dense_normalized_scores(
            result_ids=results[0].tolist(),
            result_scores=scores[0].tolist(),
            corpus_size=corpus_size,
        )
    return scores_by_label


def _ranked_chunk(
    *,
    planner_output: PlannerOutput,
    record: _ChunkRecord,
    query_bundle: QueryBundle,
    query_scores: dict[str, list[float]],
    chunk_index: int,
) -> RankedChunk:
    base_score = query_scores.get(query_bundle.base_label, [0.0])[chunk_index]
    rewrite_score_map = {
        label: query_scores[label][chunk_index]
        for label in query_bundle.rewrite_labels
    }
    best_query, best_rewrite_score = _best_rewrite(rewrite_score_map)
    query_variant_coverage_count = _support_count(
        rewrite_score_map=rewrite_score_map,
        best_rewrite_score=best_rewrite_score,
    )
    query_variant_coverage_score = _support_bonus(
        support_count=query_variant_coverage_count,
        rewrite_count=len(query_bundle.rewrite_labels),
    )
    max_query_span_score = _max_query_span_score(
        query_tokens_by_label=query_bundle.query_tokens_by_label,
        chunk_tokens=record.retrieval_tokens,
    )
    anchor_coverage_score = _anchor_coverage_score(
        anchor_terms=query_bundle.anchor_terms,
        chunk_tokens=record.retrieval_tokens,
    )

    final_score = (
        BASE_QUERY_WEIGHT * base_score
        + BEST_REWRITE_WEIGHT * best_rewrite_score
        + QUERY_VARIANT_COVERAGE_WEIGHT * query_variant_coverage_score
        + MAX_QUERY_SPAN_WEIGHT * max_query_span_score
        + ANCHOR_COVERAGE_WEIGHT * anchor_coverage_score
    )

    query_score_map = {
        query_bundle.base_label: base_score,
        **rewrite_score_map,
    }
    matched_queries = [
        label
        for label, score in query_score_map.items()
        if score > 0.0
    ]

    return RankedChunk(
        source_id=record.source.source_id,
        chunk_id=record.chunk.chunk_id,
        rank=1,
        score=ChunkScore(
            final_score=max(0.0, final_score),
            base_score=base_score,
            best_rewrite_score=best_rewrite_score,
            query_variant_coverage_score=query_variant_coverage_score,
            query_variant_coverage_count=query_variant_coverage_count,
            query_scores=query_score_map,
            matched_queries=matched_queries,
            best_query=best_query,
            max_query_span_score=max_query_span_score,
            anchor_coverage_score=anchor_coverage_score,
        ),
    )


def _best_rewrite(rewrite_score_map: dict[str, float]) -> tuple[str | None, float]:
    if not rewrite_score_map:
        return None, 0.0
    label, score = max(rewrite_score_map.items(), key=lambda item: (item[1], item[0]))
    return label, score


def _support_count(
    *,
    rewrite_score_map: dict[str, float],
    best_rewrite_score: float,
) -> int:
    if best_rewrite_score <= 0.0:
        return 0
    support_floor = REWRITE_SUPPORT_RATIO * best_rewrite_score
    return sum(1 for score in rewrite_score_map.values() if score >= support_floor)


def _support_bonus(*, support_count: int, rewrite_count: int) -> float:
    if rewrite_count <= 0:
        return 0.0
    return support_count / rewrite_count


def _anchor_terms(query_tokens_by_label: dict[str, list[str]]) -> set[str]:
    token_sets = [set(tokens) for tokens in query_tokens_by_label.values() if tokens]
    if not token_sets:
        return set()
    anchors = set(token_sets[0])
    for token_set in token_sets[1:]:
        anchors &= token_set
    return anchors


def _max_query_span_score(
    *,
    query_tokens_by_label: dict[str, list[str]],
    chunk_tokens: list[str],
) -> float:
    return max(
        (
            _ordered_query_span_score(query_tokens=query_tokens, chunk_tokens=chunk_tokens)
            for query_tokens in query_tokens_by_label.values()
        ),
        default=0.0,
    )


def _ordered_query_span_score(*, query_tokens: list[str], chunk_tokens: list[str]) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    longest_match = 0
    for query_start in range(len(query_tokens)):
        for chunk_start in range(len(chunk_tokens)):
            match_length = 0
            while (
                query_start + match_length < len(query_tokens)
                and chunk_start + match_length < len(chunk_tokens)
                and query_tokens[query_start + match_length] == chunk_tokens[chunk_start + match_length]
            ):
                match_length += 1
            if match_length > longest_match:
                longest_match = match_length
    return longest_match / len(query_tokens)


def _anchor_coverage_score(*, anchor_terms: set[str], chunk_tokens: list[str]) -> float:
    if not anchor_terms:
        return 0.0
    chunk_term_set = set(chunk_tokens)
    return len(anchor_terms & chunk_term_set) / len(anchor_terms)
