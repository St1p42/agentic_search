from __future__ import annotations

"""Jina fetch helper owned by the orchestrator."""

from typing import Protocol

from backend.app.contracts import AssessorOutput, JinaFetcherOutput


class JinaFetcher(Protocol):
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        """Fetch selected Jina pages and return page text/chunks/failure markers."""


class PlaceholderJinaFetcher:
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        _ = assessor_output
        _ = remaining_fetch_budget
        return JinaFetcherOutput(fetched_documents=[])
