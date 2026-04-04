from __future__ import annotations

"""Searcher stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import PlannerOutput, SearcherOutput


class SearcherStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None = None,
        max_search_queries: int | None = None,
    ) -> SearcherOutput:
        """Execute planner or repair/verification queries and return a bounded URL pool."""


class PlaceholderSearcherStage:
    def run(
        self,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None = None,
        max_search_queries: int | None = None,
    ) -> SearcherOutput:
        if followup_queries:
            executed_queries = list(followup_queries)
        else:
            executed_queries = [planner_output.base_query]
            executed_queries.extend(planner_output.initial_query_rewrites)

        if max_search_queries is not None:
            executed_queries = executed_queries[:max(0, max_search_queries)]

        return SearcherOutput(
            executed_queries=executed_queries,
            raw_results=[],
            shortlisted_results=[],
        )
