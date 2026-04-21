from __future__ import annotations

from pydantic import HttpUrl

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    EvidenceStore,
    ExtractorLightOutput,
    HeuristicSourceSignals,
    PlannerOutput,
    RetrievedSourcesOutput,
    SearchResultItem,
    SearcherOutput,
)
from backend.app.stages.assessor.decision_policy import SourceDecisionPolicy
from backend.app.stages.assessor.heuristic_source_assessor import HeuristicSourceAssessor
from backend.app.stages.assessor.models import HeuristicSourceAssessment
from backend.app.stages.assessor.output_builder import build_assessed_source, build_heuristic_signals


class SourceAssessmentPipeline:
    def __init__(
        self,
        *,
        heuristic_assessor: HeuristicSourceAssessor | None = None,
        decision_policy: SourceDecisionPolicy,
    ) -> None:
        self._heuristic_assessor = heuristic_assessor or HeuristicSourceAssessor()
        self._decision_policy = decision_policy

    def run(
        self,
        *,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        retrieved_sources_output: RetrievedSourcesOutput,
        extractor_light_output: ExtractorLightOutput,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
    ) -> AssessorOutput:
        shortlisted_results = searcher_output.shortlisted_results
        if not shortlisted_results:
            return AssessorOutput(
                pass_type=pass_type,
                assessed_sources=[],
                verification_gaps=[],
                selected_jina_urls=[],
            )

        heuristic_signals_by_url = self._heuristic_signals_by_url(
            planner_output=planner_output,
            extractor_light_output=extractor_light_output,
            shortlisted_results=shortlisted_results,
        )
        heuristic_assessments_by_url = self._heuristic_assessments_by_url(
            retrieved_sources_output=retrieved_sources_output,
            extractor_light_output=extractor_light_output,
            heuristic_signals_by_url=heuristic_signals_by_url,
            shortlisted_results=shortlisted_results,
        )
        decisions_by_url = self._decision_policy.decide(
            planner_output=planner_output,
            retrieved_sources_output=retrieved_sources_output,
            heuristic_signals_by_url=heuristic_signals_by_url,
            heuristic_assessments_by_url=heuristic_assessments_by_url,
            pass_type=pass_type,
            shortlisted_results=shortlisted_results,
        )
        _ = evidence_store
        _ = remaining_fetch_budget

        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[
                build_assessed_source(
                    result=result,
                    retrieved_sources_output=retrieved_sources_output,
                    heuristic_signals=heuristic_signals_by_url[result.url],
                    heuristic_assessment=heuristic_assessments_by_url[result.url],
                    decision=decisions_by_url.get(str(result.url)),
                    planner_output=planner_output,
                    pass_type=pass_type,
                )
                for result in shortlisted_results
            ],
            verification_gaps=[],
            selected_jina_urls=[],
        )

    def _heuristic_signals_by_url(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        shortlisted_results: list[SearchResultItem],
    ) -> dict[HttpUrl, HeuristicSourceSignals]:
        return {
            result.url: build_heuristic_signals(
                result=result,
                planner_output=planner_output,
                extractor_light_output=extractor_light_output,
            )
            for result in shortlisted_results
        }

    def _heuristic_assessments_by_url(
        self,
        *,
        retrieved_sources_output: RetrievedSourcesOutput,
        extractor_light_output: ExtractorLightOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        shortlisted_results: list[SearchResultItem],
    ) -> dict[HttpUrl, HeuristicSourceAssessment]:
        return {
            result.url: self._heuristic_assessor.assess(
                result=result,
                retrieved_sources_output=retrieved_sources_output,
                heuristic_signals=heuristic_signals_by_url[result.url],
                candidate_names=extractor_light_output.candidate_names,
            )
            for result in shortlisted_results
        }
