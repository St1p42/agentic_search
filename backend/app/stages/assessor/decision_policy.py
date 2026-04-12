from __future__ import annotations

from typing import Protocol

from pydantic import HttpUrl

from backend.app.contracts import AssessorPass, BraveContextOutput, HeuristicSourceSignals, PlannerOutput, SearchResultItem
from backend.app.stages.assessor.llm_source_assessor import AssessorSourceDecision, LlmSourceAssessor
from backend.app.stages.assessor.models import HeuristicSourceAssessment


class SourceDecisionPolicy(Protocol):
    def decide(
        self,
        *,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
        pass_type: AssessorPass,
        shortlisted_results: list[SearchResultItem],
    ) -> dict[str, AssessorSourceDecision]:
        """Return additional per-source decisions beyond heuristics."""


class HeuristicDecisionPolicy(SourceDecisionPolicy):
    def decide(
        self,
        *,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
        pass_type: AssessorPass,
        shortlisted_results: list[SearchResultItem],
    ) -> dict[str, AssessorSourceDecision]:
        _ = planner_output
        _ = brave_context_output
        _ = heuristic_signals_by_url
        _ = heuristic_assessments_by_url
        _ = pass_type
        _ = shortlisted_results
        return {}


class LlmDecisionPolicy(SourceDecisionPolicy):
    def __init__(self, llm_assessor: LlmSourceAssessor) -> None:
        self._llm_assessor = llm_assessor

    def decide(
        self,
        *,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
        pass_type: AssessorPass,
        shortlisted_results: list[SearchResultItem],
    ) -> dict[str, AssessorSourceDecision]:
        llm_results = [
            result
            for result in shortlisted_results
            if not heuristic_assessments_by_url[result.url].filtered_out
        ]
        return self._llm_assessor.assess(
            planner_output=planner_output,
            search_results=llm_results,
            brave_context_output=brave_context_output,
            heuristic_signals_by_url=heuristic_signals_by_url,
            heuristic_assessments_by_url=heuristic_assessments_by_url,
            pass_type=pass_type,
        )
