from __future__ import annotations

"""Searcher stage interface plus placeholder and Brave-backed implementations."""

import math
import re
from html import unescape
from typing import Protocol
from urllib.parse import urlparse

from pydantic import HttpUrl

from backend.app.api_clients import BraveSearchClient, BraveWebResult, HttpBraveSearchClient
from backend.app.config import SearcherRuntimeConfig, load_searcher_runtime_config
from backend.app.contracts import PlannerOutput, SearchResultItem, SearcherOutput


URL_FILE_EXTENSIONS = (".pdf", ".ppt", ".pptx", ".doc", ".docx")
MAX_URLS_PER_DOMAIN = 3
BOILERPLATE_SNIPPET_MARKERS = (
    "sign in to continue",
    "page not found",
    "click here",
)
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "by",
    "can",
    "company",
    "companies",
    "find",
    "for",
    "from",
    "in",
    "list",
    "me",
    "of",
    "on",
    "or",
    "show",
    "some",
    "the",
    "to",
    "top",
    "with",
    "you",
}


class SearcherStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None = None,
        max_search_queries: int | None = None,
    ) -> SearcherOutput:
        """Execute planner or repair/verification queries and return a bounded URL pool."""


class BraveSearcherStage:
    def __init__(
        self,
        runtime_config: SearcherRuntimeConfig | None = None,
        brave_client: BraveSearchClient | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._brave_client = brave_client

    def run(
        self,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None = None,
        max_search_queries: int | None = None,
    ) -> SearcherOutput:
        config = self._config()
        queries = self._select_queries(
            planner_output=planner_output,
            followup_queries=followup_queries,
            max_search_queries=max_search_queries,
        )
        if not queries:
            return self._build_output(
                executed_queries=[],
                raw_results=[],
                shortlisted_results=[],
                shortlist_cap=config.shortlist_cap,
            )

        first_pass_count = self._search_count_for_pass(
            count_map=config.initial_count_by_query_count,
            query_count=len(queries),
        )
        executed_queries, raw_results, shortlisted_results = self._run_query_batch(
            planner_output=planner_output,
            queries=queries,
            count=first_pass_count,
            existing_executed_queries=[],
            existing_raw_results=[],
        )

        if self._should_retry_weak_pool(
            shortlisted_results=shortlisted_results,
            query_count=len(queries),
            first_pass_count=first_pass_count,
            executed_queries_count=len(executed_queries),
            max_search_queries=max_search_queries,
            config=config,
        ):
            retry_count = self._search_count_for_pass(
                count_map=config.retry_count_by_query_count,
                query_count=len(queries),
            )
            executed_queries, raw_results, shortlisted_results = self._run_query_batch(
                planner_output=planner_output,
                queries=queries,
                count=retry_count,
                existing_executed_queries=executed_queries,
                existing_raw_results=raw_results,
            )

        return self._build_output(
            executed_queries=executed_queries,
            raw_results=raw_results,
            shortlisted_results=shortlisted_results,
            shortlist_cap=config.shortlist_cap,
        )

    def _config(self) -> SearcherRuntimeConfig:
        return self._runtime_config or load_searcher_runtime_config()

    def _client(self) -> BraveSearchClient:
        if self._brave_client is not None:
            return self._brave_client

        config = self._config()
        if not config.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is missing from the environment")

        self._brave_client = HttpBraveSearchClient(
            api_key=config.brave_search_api_key,
            endpoint=config.brave_search_endpoint,
            country=config.brave_country,
            search_lang=config.brave_search_lang,
        )
        return self._brave_client

    def _run_query_batch(
        self,
        *,
        planner_output: PlannerOutput,
        queries: list[str],
        count: int,
        existing_executed_queries: list[str],
        existing_raw_results: list[SearchResultItem],
    ) -> tuple[list[str], list[SearchResultItem], list[SearchResultItem]]:
        executed_queries = list(existing_executed_queries)
        raw_results = list(existing_raw_results)

        for query in queries:
            executed_queries.append(query)
            brave_results = self._client().search_web(query=query, count=count)
            raw_results.extend(_to_search_results(brave_results=brave_results, query=query))

        shortlisted_results = _build_shortlist(
            raw_results=raw_results,
            planner_output=planner_output,
            queries=queries,
            shortlist_cap=self._config().shortlist_cap,
        )
        return executed_queries, raw_results, shortlisted_results

    @staticmethod
    def _select_queries(
        *,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None,
        max_search_queries: int | None,
    ) -> list[str]:
        queries = list(followup_queries or [])
        if not queries:
            queries = [planner_output.base_query, *planner_output.initial_query_rewrites]
        queries = [" ".join(query.split()).strip() for query in queries if query.strip()]

        if max_search_queries is not None:
            queries = queries[: max(0, max_search_queries)]

        return queries

    @staticmethod
    def _search_count_for_pass(*, count_map: dict[int, int], query_count: int) -> int:
        if query_count <= 0:
            return 0
        if query_count in count_map:
            return count_map[query_count]
        return count_map[max(count_map)]

    @classmethod
    def _should_retry_weak_pool(
        cls,
        *,
        shortlisted_results: list[SearchResultItem],
        query_count: int,
        first_pass_count: int,
        executed_queries_count: int,
        max_search_queries: int | None,
        config: SearcherRuntimeConfig,
    ) -> bool:
        if len(shortlisted_results) >= config.weak_pool_threshold:
            return False

        retry_count = cls._search_count_for_pass(
            count_map=config.retry_count_by_query_count,
            query_count=query_count,
        )
        if retry_count <= first_pass_count:
            return False

        if max_search_queries is None:
            return True

        remaining_budget = max(0, max_search_queries - executed_queries_count)
        return remaining_budget >= query_count

    @staticmethod
    def _build_output(
        *,
        executed_queries: list[str],
        raw_results: list[SearchResultItem],
        shortlisted_results: list[SearchResultItem],
        shortlist_cap: int,
    ) -> SearcherOutput:
        return SearcherOutput(
            executed_queries=executed_queries,
            raw_results=raw_results,
            shortlisted_results=shortlisted_results[:shortlist_cap],
        )


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


def build_searcher_stage(
    runtime_config: SearcherRuntimeConfig | None = None,
    brave_client: BraveSearchClient | None = None,
) -> SearcherStage:
    config = runtime_config or load_searcher_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderSearcherStage()
    if config.mode == "brave":
        return BraveSearcherStage(
            runtime_config=config,
            brave_client=brave_client,
        )
    raise ValueError(f"Unsupported searcher mode: {config.mode}")


def _to_search_results(*, brave_results: list[BraveWebResult], query: str) -> list[SearchResultItem]:
    search_results: list[SearchResultItem] = []

    for result in brave_results:
        title = _normalize_text(result.title)
        snippet = _normalize_text(result.snippet)
        try:
            search_results.append(
                SearchResultItem(
                    url=HttpUrl(result.url),
                    title=title,
                    snippet=snippet,
                    domain=result.domain or urlparse(result.url).netloc,
                    rank=result.rank,
                    query_sources=[query],
                    result_type=result.result_type,
                    provider_metadata=result.provider_metadata,
                )
            )
        except ValueError:
            continue

    return search_results


def _build_shortlist(
    *,
    raw_results: list[SearchResultItem],
    planner_output: PlannerOutput,
    queries: list[str],
    shortlist_cap: int,
) -> list[SearchResultItem]:
    query_tokens, aspect_tokens = _shortlist_filter_tokens(planner_output)

    merged_by_url: dict[str, SearchResultItem] = {}
    first_seen_by_url: dict[str, int] = {}

    for index, result in enumerate(raw_results):
        if _should_prune_result(result=result, query_tokens=query_tokens, aspect_tokens=aspect_tokens):
            continue

        _merge_ranked_result(
            result=result,
            index=index,
            merged_by_url=merged_by_url,
            first_seen_by_url=first_seen_by_url,
        )

    sorted_results = _sort_merged_results(
        merged_by_url=merged_by_url,
        first_seen_by_url=first_seen_by_url,
        total_query_count=len(_ordered_unique_queries(queries)),
    )

    reserved_quota_by_query = _reserved_quota_by_query(
        queries=queries,
        base_query=planner_output.base_query,
        shortlist_cap=shortlist_cap,
    )
    return _select_shortlisted_results(
        sorted_results=sorted_results,
        queries=queries,
        reserved_quota_by_query=reserved_quota_by_query,
        shortlist_cap=shortlist_cap,
    )


def _shortlist_filter_tokens(planner_output: PlannerOutput) -> tuple[set[str], set[str]]:
    query_tokens = _tokenize(f"{planner_output.normalized_query} {planner_output.base_query}")
    aspect_tokens = (
        set().union(*[_tokenize(aspect) for aspect in planner_output.core_aspects])
        if planner_output.core_aspects
        else set()
    )
    return query_tokens, aspect_tokens


def _merge_ranked_result(
    *,
    result: SearchResultItem,
    index: int,
    merged_by_url: dict[str, SearchResultItem],
    first_seen_by_url: dict[str, int],
) -> None:
    url_key = str(result.url)
    if url_key not in merged_by_url:
        merged_by_url[url_key] = result.model_copy()
        first_seen_by_url[url_key] = index
        return

    existing = merged_by_url[url_key]
    merged_query_sources = _merge_query_sources(existing.query_sources, result.query_sources)
    if result.rank < existing.rank:
        merged_by_url[url_key] = result.model_copy(update={"query_sources": merged_query_sources})
        return

    merged_by_url[url_key] = existing.model_copy(update={"query_sources": merged_query_sources})


def _sort_merged_results(
    *,
    merged_by_url: dict[str, SearchResultItem],
    first_seen_by_url: dict[str, int],
    total_query_count: int,
) -> list[SearchResultItem]:
    return sorted(
        merged_by_url.values(),
        key=lambda item: (
            -_source_shortlist_score(item=item, total_query_count=total_query_count),
            item.rank,
            first_seen_by_url[str(item.url)],
            str(item.url),
        ),
    )


def _source_shortlist_score(*, item: SearchResultItem, total_query_count: int) -> float:
    rank_score = 1.0 / math.sqrt(max(1, item.rank))
    if total_query_count <= 0:
        source_coverage_score = 0.0
    else:
        source_coverage_score = len(item.query_sources) / total_query_count
    return (0.6 * rank_score) + (0.4 * source_coverage_score)


def _reserved_quota_by_query(
    *,
    queries: list[str],
    base_query: str,
    shortlist_cap: int,
) -> dict[str, int]:
    ordered_queries = _ordered_unique_queries(queries)
    reserved_budget = max(0, min(7, shortlist_cap - 5))
    if not ordered_queries or reserved_budget == 0:
        return {}

    weights = {
        query: (2 if query == base_query else 1)
        for query in ordered_queries
    }
    total_weight = sum(weights.values())
    quotas = {
        query: (reserved_budget * weights[query]) // total_weight
        for query in ordered_queries
    }

    remaining_slots = reserved_budget - sum(quotas.values())
    for query in sorted(
        ordered_queries,
        key=lambda item: (-weights[item], ordered_queries.index(item)),
    ):
        if remaining_slots == 0:
            break
        quotas[query] += 1
        remaining_slots -= 1

    return quotas


def _select_shortlisted_results(
    *,
    sorted_results: list[SearchResultItem],
    queries: list[str],
    reserved_quota_by_query: dict[str, int],
    shortlist_cap: int,
) -> list[SearchResultItem]:
    selected_results: list[SearchResultItem] = []
    selected_urls: set[str] = set()
    domain_counts: dict[str, int] = {}

    _fill_reserved_slots_round_robin(
        sorted_results=sorted_results,
        queries=_ordered_unique_queries(queries),
        reserved_quota_by_query=reserved_quota_by_query,
        selected_results=selected_results,
        selected_urls=selected_urls,
        domain_counts=domain_counts,
        shortlist_cap=shortlist_cap,
    )

    for result in sorted_results:
        if len(selected_results) >= shortlist_cap:
            break
        _append_if_allowed(
            result=result,
            selected_results=selected_results,
            selected_urls=selected_urls,
            domain_counts=domain_counts,
        )

    return selected_results


def _fill_reserved_slots_round_robin(
    *,
    sorted_results: list[SearchResultItem],
    queries: list[str],
    reserved_quota_by_query: dict[str, int],
    selected_results: list[SearchResultItem],
    selected_urls: set[str],
    domain_counts: dict[str, int],
    shortlist_cap: int,
) -> None:
    if not reserved_quota_by_query:
        return

    query_buckets = {
        query: [result for result in sorted_results if query in result.query_sources]
        for query in queries
    }
    query_offsets = {query: 0 for query in queries}
    filled_quota = {query: 0 for query in queries}

    while len(selected_results) < shortlist_cap:
        made_progress = False
        for query in queries:
            if filled_quota[query] >= reserved_quota_by_query.get(query, 0):
                continue

            bucket = query_buckets[query]
            while query_offsets[query] < len(bucket):
                candidate = bucket[query_offsets[query]]
                query_offsets[query] += 1
                if _append_if_allowed(
                    result=candidate,
                    selected_results=selected_results,
                    selected_urls=selected_urls,
                    domain_counts=domain_counts,
                ):
                    filled_quota[query] += 1
                    made_progress = True
                    break

            if len(selected_results) >= shortlist_cap:
                return

        if not made_progress:
            return


def _append_if_allowed(
    *,
    result: SearchResultItem,
    selected_results: list[SearchResultItem],
    selected_urls: set[str],
    domain_counts: dict[str, int],
) -> bool:
    url_key = str(result.url)
    domain_key = result.domain.lower()

    if url_key in selected_urls:
        return False
    if domain_counts.get(domain_key, 0) >= MAX_URLS_PER_DOMAIN:
        return False

    selected_results.append(result)
    selected_urls.add(url_key)
    domain_counts[domain_key] = domain_counts.get(domain_key, 0) + 1
    return True


def _ordered_unique_queries(queries: list[str]) -> list[str]:
    ordered_unique: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        ordered_unique.append(query)
    return ordered_unique


def _should_prune_result(
    *,
    result: SearchResultItem,
    query_tokens: set[str],
    aspect_tokens: set[str],
) -> bool:
    url = str(result.url)
    parsed_url = urlparse(url)
    lowered_url = url.lower()
    lowered_path = parsed_url.path.lower()
    lowered_snippet = result.snippet.lower().strip()

    if not lowered_snippet:
        return True
    if any(marker in lowered_snippet for marker in BOILERPLATE_SNIPPET_MARKERS):
        return True
    if lowered_url.endswith(URL_FILE_EXTENSIONS) or any(ext in lowered_path for ext in URL_FILE_EXTENSIONS):
        return True
    if parsed_url.netloc in {"youtube.com", "www.youtube.com", "vimeo.com", "www.vimeo.com"}:
        return True
    if _is_social_post_url(parsed_url.netloc.lower(), lowered_path):
        return True

    result_tokens = _tokenize(f"{result.title} {result.snippet}")
    if not (result_tokens & query_tokens) and not (result_tokens & aspect_tokens):
        return True

    return False


def _is_social_post_url(domain: str, path: str) -> bool:
    if domain.endswith("twitter.com") and "/status/" in path:
        return True
    if domain.endswith("facebook.com") and "/posts/" in path:
        return True
    if domain.endswith("instagram.com") and "/p/" in path:
        return True
    if domain.endswith("linkedin.com") and "/company/" not in path and (
        "/posts/" in path or "/feed/update/" in path
    ):
        return True
    return False


def _normalize_text(value: str) -> str:
    no_tags = HTML_TAG_PATTERN.sub(" ", value)
    return " ".join(unescape(no_tags).split()).strip()


def _tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if token and token not in STOPWORDS and len(token) > 1
    }


def _merge_query_sources(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for query in [*existing, *incoming]:
        if query not in seen:
            seen.add(query)
            merged.append(query)
    return merged
