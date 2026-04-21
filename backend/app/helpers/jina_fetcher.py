from __future__ import annotations

"""Jina fetch helper owned by the orchestrator."""

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from backend.app.api_clients import HttpJinaReaderClient, JinaReaderClient
from backend.app.config import JinaFetcherRuntimeConfig, load_jina_fetcher_runtime_config
from backend.app.contracts import EvidenceOrigin, PlannerOutput, RetrievedSourcesOutput, SearchResultItem, SearcherOutput, UrlSource
from backend.app.helpers.hierarchical_text_chunker import HierarchicalTextChunker
from backend.app.helpers.jina_eval_dataset_writer import (
    JinaEvalDatasetWriter,
    JsonlJinaEvalDatasetWriter,
)


class JinaFetcher(Protocol):
    def run(
        self,
        searcher_output: SearcherOutput,
        fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> RetrievedSourcesOutput:
        """Fetch selected Jina pages and return source-grouped chunked text."""


class PlaceholderJinaFetcher:
    def run(
        self,
        searcher_output: SearcherOutput,
        fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> RetrievedSourcesOutput:
        _ = searcher_output
        _ = fetch_budget
        _ = request_query
        _ = planner_output
        return RetrievedSourcesOutput(url_sources=[])


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
        searcher_output: SearcherOutput,
        fetch_budget: int,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> RetrievedSourcesOutput:
        config = self._config()
        selected_results = _selected_results(searcher_output, fetch_budget)
        if not selected_results:
            output = RetrievedSourcesOutput(url_sources=[])
            if request_query and planner_output:
                self._eval_dataset_writer.write(
                    request_query=request_query,
                    planner_output=planner_output,
                    url_sources=output.url_sources,
                )
            return output

        max_workers = max(1, min(config.max_concurrency, len(selected_results)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self._process_result, index=index, result=result, config=config)
                for index, result in enumerate(selected_results)
            ]
            indexed_url_sources = [future.result() for future in futures]

        indexed_url_sources.sort(key=lambda item: item[0])
        url_sources = [url_source for _, url_source in indexed_url_sources]

        output = RetrievedSourcesOutput(url_sources=url_sources)
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

    def _process_result(
        self,
        *,
        index: int,
        result: SearchResultItem,
        config: JinaFetcherRuntimeConfig,
    ) -> tuple[int, UrlSource]:
        source_id = _source_id(origin=EvidenceOrigin.JINA, source_url=str(result.url))
        chunker = HierarchicalTextChunker(
            target_chunk_chars=config.max_chars_per_chunk,
            min_chunk_chars=config.min_chars_per_chunk,
            max_chunks=config.max_chunks_per_doc,
        )
        try:
            document = self._client().fetch_url(url=str(result.url))
            chunks = chunker.chunk(text=document.text, source_id=source_id)
            return (
                index,
                UrlSource(
                    source_id=source_id,
                    url=result.url,
                    title=document.title,
                    origin=EvidenceOrigin.JINA,
                    chunks=chunks,
                ),
            )
        except Exception as exc:
            return (
                index,
                UrlSource(
                    source_id=source_id,
                    url=result.url,
                    title=result.title,
                    origin=EvidenceOrigin.JINA,
                    metadata={"fetch_succeeded": False, "error_message": str(exc)},
                    chunks=[],
                ),
            )


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


def _selected_results(searcher_output: SearcherOutput, fetch_budget: int) -> list[SearchResultItem]:
    return searcher_output.shortlisted_results[: max(0, fetch_budget)]
