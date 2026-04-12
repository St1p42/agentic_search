from __future__ import annotations

"""Canonicalizer+Verifier+Evaluator stage interface and thin deterministic finalizer."""

from typing import Protocol

from backend.app.contracts import (
    CanonicalEntity,
    CanonicalizerVerifierEvaluatorOutput,
    ExtractedEntity,
    ExtractorOutput,
    PlannerOutput,
)
from backend.app.stages.final_row_pruner import FinalRowPruner
from backend.app.stages.final_row_reranker import FinalRowReranker


class CanonicalizerVerifierEvaluatorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
    ) -> CanonicalizerVerifierEvaluatorOutput:
        """Merge/verify/rank candidate rows for the final user-facing response."""


class PlaceholderCanonicalizerVerifierEvaluatorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
    ) -> CanonicalizerVerifierEvaluatorOutput:
        _ = planner_output
        _ = extractor_output
        return CanonicalizerVerifierEvaluatorOutput(final_rows=[])


class ThinFinalizerStage:
    def __init__(
        self,
        pruner: FinalRowPruner | None = None,
        reranker: FinalRowReranker | None = None,
    ) -> None:
        self._pruner = pruner or FinalRowPruner()
        self._reranker = reranker or FinalRowReranker()

    def run(
        self,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
    ) -> CanonicalizerVerifierEvaluatorOutput:
        _ = planner_output
        canonical_rows = [_canonical_entity(entity) for entity in extractor_output.entities]
        surviving_rows = self._pruner.prune(canonical_rows)
        return CanonicalizerVerifierEvaluatorOutput(
            final_rows=self._reranker.rerank(surviving_rows)
        )


def _canonical_entity(entity: ExtractedEntity) -> CanonicalEntity:
    return CanonicalEntity(
        name=entity.entity_name,
        fields=entity.fields,
        source_urls=entity.source_urls,
    )
