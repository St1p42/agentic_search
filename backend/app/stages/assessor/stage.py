from __future__ import annotations

from typing import Protocol

from backend.app.api_clients import StructuredLlmClient
from backend.app.config import AssessorRuntimeConfig, load_assessor_runtime_config
from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    EvidenceStore,
    ExtractorLightOutput,
    PlannerOutput,
    RetrievedSourcesOutput,
    SearcherOutput,
)
from backend.app.stages.assessor.decision_policy import HeuristicDecisionPolicy, LlmDecisionPolicy
from backend.app.stages.assessor.heuristic_source_assessor import HeuristicSourceAssessor
from backend.app.stages.assessor.llm_source_assessor import LlmSourceAssessor
from backend.app.stages.assessor.pipeline import SourceAssessmentPipeline


class SourceAssessorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        extractor_light_output: ExtractorLightOutput,
        retrieved_sources_output: RetrievedSourcesOutput | None = None,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> AssessorOutput:
        """Classify shortlisted sources for first-pass downstream extraction."""


class PlaceholderSourceAssessorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        extractor_light_output: ExtractorLightOutput,
        retrieved_sources_output: RetrievedSourcesOutput | None = None,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> AssessorOutput:
        _ = planner_output
        _ = searcher_output
        _ = retrieved_sources_output
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


class HeuristicSourceAssessorStage:
    def __init__(
        self,
        heuristic_assessor: HeuristicSourceAssessor | None = None,
        pipeline: SourceAssessmentPipeline | None = None,
    ) -> None:
        self._pipeline = pipeline or SourceAssessmentPipeline(
            heuristic_assessor=heuristic_assessor,
            decision_policy=HeuristicDecisionPolicy(),
        )

    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        extractor_light_output: ExtractorLightOutput,
        retrieved_sources_output: RetrievedSourcesOutput | None = None,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> AssessorOutput:
        return self._pipeline.run(
            planner_output=planner_output,
            searcher_output=searcher_output,
            retrieved_sources_output=retrieved_sources_output or brave_context_output or RetrievedSourcesOutput(),
            extractor_light_output=extractor_light_output,
            pass_type=pass_type,
            evidence_store=evidence_store,
            remaining_fetch_budget=remaining_fetch_budget,
        )


class LlmSourceAssessorStage:
    def __init__(
        self,
        model: str,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: AssessorRuntimeConfig | None = None,
        heuristic_assessor: HeuristicSourceAssessor | None = None,
    ) -> None:
        self._pipeline = SourceAssessmentPipeline(
            heuristic_assessor=heuristic_assessor,
            decision_policy=LlmDecisionPolicy(
                LlmSourceAssessor(
                    model=model,
                    llm_client=llm_client,
                    runtime_config=runtime_config,
                )
            ),
        )

    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        extractor_light_output: ExtractorLightOutput,
        retrieved_sources_output: RetrievedSourcesOutput | None = None,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> AssessorOutput:
        return self._pipeline.run(
            planner_output=planner_output,
            searcher_output=searcher_output,
            retrieved_sources_output=retrieved_sources_output or brave_context_output or RetrievedSourcesOutput(),
            extractor_light_output=extractor_light_output,
            pass_type=pass_type,
            evidence_store=evidence_store,
            remaining_fetch_budget=remaining_fetch_budget,
        )


def build_source_assessor_stage(
    runtime_config: AssessorRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> SourceAssessorStage:
    config = runtime_config or load_assessor_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderSourceAssessorStage()
    if config.mode == "heuristic":
        return HeuristicSourceAssessorStage()
    if config.mode == "llm":
        return LlmSourceAssessorStage(
            model=config.model,
            llm_client=llm_client,
            runtime_config=config,
        )
    raise ValueError(f"Unsupported assessor mode: {config.mode}")
