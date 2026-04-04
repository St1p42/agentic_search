from __future__ import annotations

"""Planner stage interface and placeholder implementation."""

from typing import Protocol

from backend.app.contracts import PlannerOutput


class PlannerStage(Protocol):
    def run(self, query: str) -> PlannerOutput:
        """Return a query plan for downstream retrieval and extraction."""


class PlaceholderPlannerStage:
    def run(self, query: str) -> PlannerOutput:
        return PlannerOutput(
            entity_type="unknown_entity",
            query_mode="general_web",
            schema_columns=["name", "summary", "website"],
            core_aspects=["identity", "summary"],
            base_query=query,
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query=query,
        )
