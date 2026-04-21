from __future__ import annotations

"""Pure output-merging helper for orchestrator sub-pass results."""

from typing import Protocol

from backend.app.contracts import (
    AssessorOutput,
    BraveContextOutput,
    BraveContextPassage,
    RetrievedChunk,
    SearcherOutput,
    UrlSource,
)


class OutputMerger(Protocol):
    def merge_searcher_outputs(
        self,
        primary_output: SearcherOutput,
        extra_output: SearcherOutput,
    ) -> SearcherOutput:
        """Merge first-pass and verification-pass search outputs."""

    def merge_brave_context_outputs(
        self,
        primary_output: BraveContextOutput,
        extra_output: BraveContextOutput,
    ) -> BraveContextOutput:
        """Merge first-pass and verification-pass Brave context outputs."""

    def merge_assessor_outputs(
        self,
        primary_output: AssessorOutput,
        extra_output: AssessorOutput,
    ) -> AssessorOutput:
        """Merge first-pass and verification/Jina-selection assessor outputs."""


class DefaultOutputMerger:
    def merge_searcher_outputs(
        self,
        primary_output: SearcherOutput,
        extra_output: SearcherOutput,
    ) -> SearcherOutput:
        return SearcherOutput(
            executed_queries=[*primary_output.executed_queries, *extra_output.executed_queries],
            raw_results=[*primary_output.raw_results, *extra_output.raw_results],
            shortlisted_results=[
                *primary_output.shortlisted_results,
                *extra_output.shortlisted_results,
            ],
        )

    def merge_brave_context_outputs(
        self,
        primary_output: BraveContextOutput,
        extra_output: BraveContextOutput,
    ) -> BraveContextOutput:
        passages_by_url: dict[str, list[BraveContextPassage]] = {
            str(url): [*passages]
            for url, passages in primary_output.passages_by_url.items()
        }
        for url, passages in extra_output.passages_by_url.items():
            url_key = str(url)
            if url_key not in passages_by_url:
                passages_by_url[url_key] = []
            passages_by_url[url_key].extend(passages)
        retrieved_chunks_by_url: dict[str, list[RetrievedChunk]] = {
            str(url): [*chunks]
            for url, chunks in primary_output.retrieved_chunks_by_url.items()
        }
        for url, chunks in extra_output.retrieved_chunks_by_url.items():
            url_key = str(url)
            if url_key not in retrieved_chunks_by_url:
                retrieved_chunks_by_url[url_key] = []
            retrieved_chunks_by_url[url_key].extend(chunks)
        url_sources: list[UrlSource] = [*primary_output.url_sources, *extra_output.url_sources]
        return BraveContextOutput(
            passages_by_url=passages_by_url,
            retrieved_chunks_by_url=retrieved_chunks_by_url,
            url_sources=url_sources,
        )

    def merge_assessor_outputs(
        self,
        primary_output: AssessorOutput,
        extra_output: AssessorOutput,
    ) -> AssessorOutput:
        return AssessorOutput(
            pass_type=extra_output.pass_type,
            assessed_sources=[*primary_output.assessed_sources, *extra_output.assessed_sources],
            verification_gaps=extra_output.verification_gaps or primary_output.verification_gaps,
            selected_jina_urls=extra_output.selected_jina_urls or primary_output.selected_jina_urls,
        )
