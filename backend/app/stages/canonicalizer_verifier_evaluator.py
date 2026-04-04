from __future__ import annotations

"""Canonicalizer+Verifier+Evaluator stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import (
    CanonicalizerVerifierEvaluatorOutput,
    ExtractorOutput,
    PlannerOutput,
    RepairDiagnostics,
)


class CanonicalizerVerifierEvaluatorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
    ) -> CanonicalizerVerifierEvaluatorOutput:
        """Merge/verify/rank candidate rows and emit repair diagnostics."""


class PlaceholderCanonicalizerVerifierEvaluatorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
    ) -> CanonicalizerVerifierEvaluatorOutput:
        _ = planner_output
        _ = extractor_output
        return CanonicalizerVerifierEvaluatorOutput(
            final_rows=[],
            diagnostics=RepairDiagnostics(
                num_strong_entities=0,
                aspect_coverage_by_aspect={},
                missing_key_fields_rate=1.0,
                redundancy_score=0.0,
                verification_source_coverage=0.0,
                repair_recommended=False,
                repair_reason=None,
                missing_aspects=[],
                weak_fields=[],
                suggested_followup_queries=[],
            ),
        )
