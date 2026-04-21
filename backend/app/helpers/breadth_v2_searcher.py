from __future__ import annotations

from dataclasses import dataclass

from backend.app.api_clients import BraveSearchClient, HttpBraveSearchClient
from backend.app.config import SearcherRuntimeConfig, load_searcher_runtime_config
from backend.app.contracts import PlannerOutput, SearchResultItem, SearcherOutput
from backend.app.helpers.search_result_utils import (
    merged_results,
    to_search_results,
)


DEFAULT_BREADTH_V2_SOURCES_PER_QUERY = 5
DEFAULT_BREADTH_V2_SHORTLIST_CAP = 15


@dataclass(frozen=True)
class BreadthV2SearchConfig:
    sources_per_query: int = DEFAULT_BREADTH_V2_SOURCES_PER_QUERY
    shortlist_cap: int = DEFAULT_BREADTH_V2_SHORTLIST_CAP


class BreadthV2Searcher:
    def __init__(
        self,
        *,
        runtime_config: SearcherRuntimeConfig | None = None,
        brave_client: BraveSearchClient | None = None,
        search_config: BreadthV2SearchConfig | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._brave_client = brave_client
        self._search_config = search_config or BreadthV2SearchConfig()

    def run(
        self,
        *,
        planner_output: PlannerOutput,
        queries: list[str],
    ) -> SearcherOutput:
        normalized_queries = [
            " ".join(query.split()).strip()
            for query in queries
            if query.strip()
        ][: self._search_config.shortlist_cap]
        if not normalized_queries:
            return SearcherOutput(executed_queries=[], raw_results=[], shortlisted_results=[])

        raw_results: list[SearchResultItem] = []
        for query in normalized_queries:
            brave_results = self._client().search_web(
                query=query,
                count=self._search_config.sources_per_query,
            )
            raw_results.extend(to_search_results(brave_results=brave_results, query=query))

        merged_result_items, _ = merged_results(
            raw_results=raw_results,
            planner_output=planner_output,
            queries=normalized_queries,
        )
        shortlisted_results = merged_result_items[: self._search_config.shortlist_cap]
        return SearcherOutput(
            executed_queries=normalized_queries,
            raw_results=raw_results,
            shortlisted_results=shortlisted_results,
        )

    def _client(self) -> BraveSearchClient:
        if self._brave_client is not None:
            return self._brave_client

        config = self._runtime_config or load_searcher_runtime_config()
        if not config.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is missing from the environment")

        self._brave_client = HttpBraveSearchClient(
            api_key=config.brave_search_api_key,
            endpoint=config.brave_search_endpoint,
            country=config.brave_country,
            search_lang=config.brave_search_lang,
        )
        return self._brave_client
