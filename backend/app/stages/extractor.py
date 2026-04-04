from __future__ import annotations

"""Extractor stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import EvidenceStore, ExtractorLightOutput, ExtractorOutput, PlannerOutput


class ExtractorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
    ) -> ExtractorOutput:
        """Extract structured candidate entities from entity-centric evidence chunks."""


class PlaceholderExtractorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
    ) -> ExtractorOutput:
        _ = planner_output
        _ = extractor_light_output
        _ = evidence_store
        return prior_output or ExtractorOutput(entities=[])
