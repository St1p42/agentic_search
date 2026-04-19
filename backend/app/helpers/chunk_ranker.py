from __future__ import annotations

"""Request-scoped chunk ranking over retrieved URL sources."""

from dataclasses import dataclass
from typing import Protocol

import bm25s

from backend.app.contracts import (
    ChunkRankingOutput,
    PlannerOutput,
    RetrievedChunk,
    ScoredChunk,
    UrlSource,
)
from backend.app.helpers.chunk_retrieval_preprocessor import (
    ChunkRetrievalPreprocessor,
    DefaultChunkRetrievalPreprocessor,
)


BASE_QUERY_WEIGHT = 0.45
BEST_REWRITE_WEIGHT = 0.45
SUPPORT_BONUS_WEIGHT = 0.10
REWRITE_SUPPORT_RATIO = 0.80


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


class DefaultChunkRanker:
    def __init__(
        self,
        *,
        preprocessor: ChunkRetrievalPreprocessor | None = None,
    ) -> None:
        self._preprocessor = preprocessor or DefaultChunkRetrievalPreprocessor()

    def run(
        self,
        planner_output: PlannerOutput,
        url_sources: list[UrlSource],
    ) -> ChunkRankingOutput:
        chunk_records = [
            _ChunkRecord(
                source=source,
                chunk=chunk,
            )
            for source in url_sources
            for chunk in source.chunks
            if chunk.text.strip()
        ]
        if not chunk_records:
            return ChunkRankingOutput(scored_chunks=[])

        corpus_tokens = self._preprocessor.preprocess_texts(
            [record.chunk.text for record in chunk_records]
        )
        retriever = bm25s.BM25()
        retriever.index(corpus_tokens)

        queries = _query_bundle(planner_output)
        query_scores = _query_scores(
            retriever=retriever,
            query_bundle=queries,
            preprocessor=self._preprocessor,
            corpus_size=len(chunk_records),
        )

        scored_chunks = [
            _scored_chunk(
                planner_output=planner_output,
                record=record,
                query_bundle=queries,
                query_scores=query_scores,
                chunk_index=index,
            )
            for index, record in enumerate(chunk_records)
        ]
        scored_chunks.sort(key=lambda chunk: (-chunk.final_score, chunk.source_id, chunk.chunk_id))
        return ChunkRankingOutput(scored_chunks=scored_chunks)

@dataclass(frozen=True)
class _ChunkRecord:
    source: UrlSource
    chunk: RetrievedChunk


def _query_bundle(planner_output: PlannerOutput) -> QueryBundle:
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
    return QueryBundle(
        base_label="base",
        query_text_by_label=query_text_by_label,
        rewrite_labels=rewrite_labels,
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
        scores_by_label[label] = _dense_normalized_scores(
            result_ids=results[0].tolist(),
            result_scores=scores[0].tolist(),
            corpus_size=corpus_size,
        )
    return scores_by_label


def _dense_normalized_scores(
    *,
    result_ids: list[int],
    result_scores: list[float],
    corpus_size: int,
) -> list[float]:
    dense_scores = [0.0] * corpus_size
    for doc_id, score in zip(result_ids, result_scores, strict=False):
        if 0 <= doc_id < corpus_size:
            dense_scores[doc_id] = score
    max_score = max(dense_scores, default=0.0)
    if max_score <= 0.0:
        return dense_scores
    return [max(0.0, score / max_score) for score in dense_scores]


def _scored_chunk(
    *,
    planner_output: PlannerOutput,
    record: _ChunkRecord,
    query_bundle: QueryBundle,
    query_scores: dict[str, list[float]],
    chunk_index: int,
) -> ScoredChunk:
    base_score = query_scores.get(query_bundle.base_label, [0.0])[chunk_index]
    rewrite_score_map = {
        label: query_scores[label][chunk_index]
        for label in query_bundle.rewrite_labels
    }
    best_query, best_rewrite_score = _best_rewrite(rewrite_score_map)
    support_count = _support_count(
        rewrite_score_map=rewrite_score_map,
        best_rewrite_score=best_rewrite_score,
    )
    support_bonus = _support_bonus(
        support_count=support_count,
        rewrite_count=len(query_bundle.rewrite_labels),
    )

    final_score = (
        BASE_QUERY_WEIGHT * base_score
        + BEST_REWRITE_WEIGHT * best_rewrite_score
        + SUPPORT_BONUS_WEIGHT * support_bonus
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

    return ScoredChunk(
        chunk_id=record.chunk.chunk_id,
        source_id=record.source.source_id,
        source_url=record.source.url,
        source_title=record.source.title,
        text=record.chunk.text,
        base_score=base_score,
        best_rewrite_score=best_rewrite_score,
        support_bonus=support_bonus,
        support_count=support_count,
        query_scores=query_score_map,
        matched_queries=matched_queries,
        best_query=best_query,
        aspect_overlap_score=0.0,
        title_overlap_score=0.0,
        official_domain_boost=0.0,
        boilerplate_penalty=0.0,
        final_score=max(0.0, final_score),
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
