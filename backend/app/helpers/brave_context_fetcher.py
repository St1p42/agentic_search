from __future__ import annotations

"""Brave LLM Context fetch helper owned by the orchestrator."""

from typing import Protocol

from backend.app.contracts import BraveContextOutput, SearcherOutput


class BraveContextFetcher(Protocol):
    def run(self, searcher_output: SearcherOutput) -> BraveContextOutput:
        """Fetch URL-linked Brave LLM Context passages for shortlisted URLs."""


class PlaceholderBraveContextFetcher:
    def run(self, searcher_output: SearcherOutput) -> BraveContextOutput:
        _ = searcher_output
        return BraveContextOutput(passages_by_url={})
