from __future__ import annotations

"""Assessor stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    EvidenceStore,
    ExtractorLightOutput,
    PlannerOutput,
    SearcherOutput,
)


class AssessorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
    ) -> AssessorOutput:
        """Classify sources, detect verification gaps, and/or select Jina URLs."""


class PlaceholderAssessorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
    ) -> AssessorOutput:
        _ = planner_output
        _ = searcher_output
        _ = brave_context_output
        _ = extractor_light_output
        _ = evidence_store
        _ = remaining_fetch_budget
        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[],
            verification_gaps=[],
            selected_jina_urls=[],
        )
