from __future__ import annotations

"""Jina fetch helper owned by the orchestrator."""

from typing import Protocol

from backend.app.api_clients import HttpJinaReaderClient, JinaReaderClient
from backend.app.config import JinaFetcherRuntimeConfig, load_jina_fetcher_runtime_config
from backend.app.contracts import AssessorOutput, EvidenceOrigin, JinaFetcherOutput, PlannerOutput, UrlSource
from backend.app.helpers.hierarchical_text_chunker import HierarchicalTextChunker
from backend.app.helpers.jina_eval_dataset_writer import (
    JinaEvalDatasetWriter,
    JsonlJinaEvalDatasetWriter,
)


class JinaFetcher(Protocol):
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> JinaFetcherOutput:
        """Fetch selected Jina pages and return source-grouped chunked text."""


class PlaceholderJinaFetcher:
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> JinaFetcherOutput:
        _ = assessor_output
        _ = remaining_fetch_budget
        _ = request_query
        _ = planner_output
        return JinaFetcherOutput(url_sources=[])


class DefaultJinaFetcher:
    def __init__(
        self,
        runtime_config: JinaFetcherRuntimeConfig | None = None,
        jina_reader_client: JinaReaderClient | None = None,
        eval_dataset_writer: JinaEvalDatasetWriter | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._jina_reader_client = jina_reader_client
        self._eval_dataset_writer = eval_dataset_writer or JsonlJinaEvalDatasetWriter()

    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> JinaFetcherOutput:
        config = self._config()
        chunker = HierarchicalTextChunker(
            target_chunk_chars=config.max_chars_per_chunk,
            min_chunk_chars=config.min_chars_per_chunk,
            max_chunks=config.max_chunks_per_doc,
        )
        selected_urls = assessor_output.selected_jina_urls[: max(0, remaining_fetch_budget)]
        url_sources: list[UrlSource] = []

        for selected_url in selected_urls:
            source_id = _source_id(origin=EvidenceOrigin.JINA, source_url=str(selected_url))
            try:
                document = self._client().fetch_url(url=str(selected_url))
                chunks = chunker.chunk(text=document.text, source_id=source_id)
                url_sources.append(
                    UrlSource(
                        source_id=source_id,
                        url=selected_url,
                        title=document.title,
                        origin=EvidenceOrigin.JINA,
                        chunks=chunks,
                    )
                )
            except Exception as exc:
                url_sources.append(
                    UrlSource(
                        source_id=source_id,
                        url=selected_url,
                        title=str(selected_url),
                        origin=EvidenceOrigin.JINA,
                        metadata={"fetch_succeeded": False, "error_message": str(exc)},
                        chunks=[],
                    )
                )

        output = JinaFetcherOutput(url_sources=url_sources)
        if request_query and planner_output:
            self._eval_dataset_writer.write(
                request_query=request_query,
                planner_output=planner_output,
                url_sources=output.url_sources,
            )
        return output

    def _config(self) -> JinaFetcherRuntimeConfig:
        return self._runtime_config or load_jina_fetcher_runtime_config()

    def _client(self) -> JinaReaderClient:
        if self._jina_reader_client is not None:
            return self._jina_reader_client

        config = self._config()
        self._jina_reader_client = HttpJinaReaderClient(
            base_url=config.reader_base_url,
            api_key=config.jina_api_key,
            timeout_seconds=config.timeout_seconds,
        )
        return self._jina_reader_client


def build_jina_fetcher(
    runtime_config: JinaFetcherRuntimeConfig | None = None,
    jina_reader_client: JinaReaderClient | None = None,
    eval_dataset_writer: JinaEvalDatasetWriter | None = None,
) -> JinaFetcher:
    config = runtime_config or load_jina_fetcher_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderJinaFetcher()
    if config.mode == "jina":
        return DefaultJinaFetcher(
            runtime_config=config,
            jina_reader_client=jina_reader_client,
            eval_dataset_writer=eval_dataset_writer,
        )
    raise ValueError(f"Unsupported Jina fetcher mode: {config.mode}")


def _source_id(*, origin: EvidenceOrigin, source_url: str) -> str:
    return f"{origin.value}:{source_url}"
