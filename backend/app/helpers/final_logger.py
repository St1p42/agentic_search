from __future__ import annotations

"""Compact server-side logging for final pipeline summaries."""

import json
import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from backend.app.contracts import (
    CanonicalizerVerifierEvaluatorOutput,
    ChunkRankingOutput,
    ExtractorOutput,
    ExtractorLightOutput,
    PlannerOutput,
)

if TYPE_CHECKING:
    from backend.app.helpers.entity_reranker import EntityRankingResult, RankedEntity


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
        entity_ranking_result: "EntityRankingResult | None",
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
        breadth_v2_debug: dict[str, object] | None = None,
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
        entity_ranking_result: "EntityRankingResult | None",
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
        breadth_v2_debug: dict[str, object] | None = None,
    ) -> None:
        _ = request_id
        _ = planner_output
        _ = chunk_ranking_output
        _ = extractor_light_output
        _ = entity_ranking_result
        _ = extractor_output
        _ = finalizer_output
        _ = breadth_v2_debug


class DefaultFinalLogger(FinalLogger):
    def log_summary(
        self,
        *,
        request_id: str,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput | None,
        extractor_light_output: ExtractorLightOutput | None,
        entity_ranking_result: "EntityRankingResult | None",
        extractor_output: ExtractorOutput | None,
        finalizer_output: CanonicalizerVerifierEvaluatorOutput | None,
        breadth_v2_debug: dict[str, object] | None = None,
    ) -> None:
        payload = {
            "request_id": request_id,
            "normalized_query": planner_output.normalized_query,
            "base_query": planner_output.base_query,
            "query_rewrites": planner_output.initial_query_rewrites,
            "initial_entity_columns": self._populated_extracted_columns(extractor_output),
            "selected_sources": self._selected_sources(chunk_ranking_output),
            "top_candidates": self._top_candidates(extractor_light_output),
            "ranked_entities_debug": self._ranked_entities_debug(entity_ranking_result),
            "final_entities": self._final_entities(finalizer_output),
        }
        logger.warning("pipeline_debug_summary %s", json.dumps(payload, ensure_ascii=True, sort_keys=True))
        if breadth_v2_debug:
            enrichment_payload = {
                "request_id": request_id,
                "normalized_query": planner_output.normalized_query,
                "base_query": planner_output.base_query,
                **breadth_v2_debug,
            }
            logger.warning(
                "breadth_v2_debug_summary %s",
                json.dumps(enrichment_payload, ensure_ascii=True, sort_keys=True),
            )

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
    def _ranked_entities_debug(
        entity_ranking_result: "EntityRankingResult | None",
    ) -> list[dict[str, float | int | str | list[str]]]:
        if entity_ranking_result is None:
            return []

        ranked_entities = [
            *entity_ranking_result.kept_entities,
            *entity_ranking_result.filtered_entities,
        ]
        return [
            DefaultFinalLogger._ranked_entity_payload(entity, kept=index < len(entity_ranking_result.kept_entities))
            for index, entity in enumerate(ranked_entities)
        ]

    @staticmethod
    def _ranked_entity_payload(
        entity: "RankedEntity",
        *,
        kept: bool,
    ) -> dict[str, float | int | str | list[str]]:
        return {
            "name": entity.entity_name,
            "kept": "yes" if kept else "no",
            "candidate_type": entity.candidate_type,
            "final_score": round(entity.final_score, 4),
            "support_score": round(entity.support_score, 4),
            "query_alignment_score": round(entity.query_alignment_score, 4),
            "dominant_query_variant": entity.dominant_query_variant or "",
            "supporting_query_variants": entity.supporting_query_variants,
            "unique_source_count": entity.features.unique_source_count,
            "query_variant_coverage_count": entity.features.query_variant_coverage_count,
        }

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
