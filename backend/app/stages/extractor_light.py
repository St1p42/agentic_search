from __future__ import annotations

"""ExtractorLight stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import BraveContextOutput, ExtractorLightOutput, PlannerOutput


class ExtractorLightStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        """Extract candidate names only and map those names to mentioning URLs."""


class PlaceholderExtractorLightStage:
    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        _ = planner_output
        _ = brave_context_output
        return ExtractorLightOutput(
            candidate_names=[],
            name_to_source_urls={},
            mention_counts={},
        )
