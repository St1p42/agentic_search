from __future__ import annotations

"""Compact server-side logging for final pipeline summaries."""

import json
import logging
from abc import ABC, abstractmethod

from backend.app.contracts import (
    CanonicalizerVerifierEvaluatorOutput,
    ChunkRankingOutput,
    ExtractorOutput,
    ExtractorLightOutput,
    PlannerOutput,
)


logger = logging.getLogger(__name__)


class FinalLogger(ABC):
    @abstractmethod
    def log_summary(
        self,
        *,
        request_id: str,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput | None,
        extractor_light_output: ExtractorLightOutput | None,
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
    ) -> None:
        """Log a compact per-request pipeline summary."""


class PlaceholderFinalLogger(FinalLogger):
    def log_summary(
        self,
        *,
        request_id: str,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput | None,
        extractor_light_output: ExtractorLightOutput | None,
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
    ) -> None:
        _ = request_id
        _ = planner_output
        _ = chunk_ranking_output
        _ = extractor_light_output
        _ = extractor_output
        _ = finalizer_output


class DefaultFinalLogger(FinalLogger):
    def log_summary(
        self,
        *,
        request_id: str,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput | None,
        extractor_light_output: ExtractorLightOutput | None,
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
    ) -> None:
        payload = {
            "request_id": request_id,
            "normalized_query": planner_output.normalized_query,
            "base_query": planner_output.base_query,
            "query_rewrites": planner_output.initial_query_rewrites,
            "initial_entity_columns": self._populated_extracted_columns(extractor_output),
            "selected_sources": self._selected_sources(chunk_ranking_output),
            "top_candidates": self._top_candidates(extractor_light_output),
            "final_entities": self._final_entities(finalizer_output),
        }
        logger.warning("pipeline_debug_summary %s", json.dumps(payload, ensure_ascii=True, sort_keys=True))

    @staticmethod
    def _selected_sources(chunk_ranking_output: ChunkRankingOutput | None) -> list[str]:
        if chunk_ranking_output is None or not chunk_ranking_output.selected_chunk_ids:
            return []

        selected_chunk_ids = set(chunk_ranking_output.selected_chunk_ids)
        source_urls_by_id = {
            source.source_id: str(source.url)
            for source in chunk_ranking_output.url_sources
        }

        selected_sources: list[str] = []
        seen_urls: set[str] = set()
        for ranked_chunk in chunk_ranking_output.ranked_chunks:
            if ranked_chunk.chunk_id not in selected_chunk_ids:
                continue
            source_url = source_urls_by_id.get(ranked_chunk.source_id)
            if source_url is None or source_url in seen_urls:
                continue
            selected_sources.append(source_url)
            seen_urls.add(source_url)
        return selected_sources

    @staticmethod
    def _top_candidates(extractor_light_output: ExtractorLightOutput | None) -> list[dict[str, int | str]]:
        if extractor_light_output is None:
            return []

        candidates = sorted(
            extractor_light_output.candidate_names,
            key=lambda name: (-extractor_light_output.mention_counts.get(name, 0), name.casefold()),
        )
        return [
            {"name": name, "mentions": extractor_light_output.mention_counts.get(name, 0)}
            for name in candidates[:10]
        ]

    @staticmethod
    def _final_entities(
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
    ) -> list[str]:
        if finalizer_output is None:
            return []
        return [row.name for row in finalizer_output.final_rows]

    @staticmethod
    def _populated_extracted_columns(extractor_output: ExtractorOutput | None) -> list[str]:
        if extractor_output is None:
            return []

        populated_columns = {
            column_name
            for entity in extractor_output.entities
            for column_name, field_value in entity.fields.items()
            if field_value.value is not None
        }
        return sorted(populated_columns)
