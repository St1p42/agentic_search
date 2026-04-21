from __future__ import annotations

import math
import re
from html import unescape
from urllib.parse import urlparse

from pydantic import HttpUrl

from backend.app.api_clients import BraveWebResult
from backend.app.contracts import PlannerOutput, SearchResultItem


URL_FILE_EXTENSIONS = (".pdf", ".ppt", ".pptx", ".doc", ".docx")
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


def to_search_results(*, brave_results: list[BraveWebResult], query: str) -> list[SearchResultItem]:
    search_results: list[SearchResultItem] = []

    for result in brave_results:
        title = normalize_text(result.title)
        snippet = normalize_text(result.snippet)
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


def merged_results(
    *,
    raw_results: list[SearchResultItem],
    planner_output: PlannerOutput,
    queries: list[str],
) -> tuple[list[SearchResultItem], dict[str, int]]:
    query_tokens, aspect_tokens = shortlist_filter_tokens(planner_output)

    merged_by_url: dict[str, SearchResultItem] = {}
    first_seen_by_url: dict[str, int] = {}
    pruned_results_count = 0

    for index, result in enumerate(raw_results):
        if should_prune_result(result=result, query_tokens=query_tokens, aspect_tokens=aspect_tokens):
            pruned_results_count += 1
            continue

        merge_ranked_result(
            result=result,
            index=index,
            merged_by_url=merged_by_url,
            first_seen_by_url=first_seen_by_url,
        )

    sorted_results = sort_merged_results(
        merged_by_url=merged_by_url,
        first_seen_by_url=first_seen_by_url,
        total_query_count=len(ordered_unique_queries(queries)),
    )

    return sorted_results, {"pruned_results_count": pruned_results_count}


def shortlist_filter_tokens(planner_output: PlannerOutput) -> tuple[set[str], set[str]]:
    query_tokens = tokenize(f"{planner_output.normalized_query} {planner_output.base_query}")
    aspect_tokens = (
        set().union(*[tokenize(aspect) for aspect in planner_output.core_aspects])
        if planner_output.core_aspects
        else set()
    )
    return query_tokens, aspect_tokens


def merge_ranked_result(
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
    merged_query_sources = merge_query_sources(existing.query_sources, result.query_sources)
    if result.rank < existing.rank:
        merged_by_url[url_key] = result.model_copy(update={"query_sources": merged_query_sources})
        return

    merged_by_url[url_key] = existing.model_copy(update={"query_sources": merged_query_sources})


def sort_merged_results(
    *,
    merged_by_url: dict[str, SearchResultItem],
    first_seen_by_url: dict[str, int],
    total_query_count: int,
) -> list[SearchResultItem]:
    return sorted(
        merged_by_url.values(),
        key=lambda item: (
            -source_shortlist_score(item=item, total_query_count=total_query_count),
            item.rank,
            first_seen_by_url[str(item.url)],
            str(item.url),
        ),
    )


def source_shortlist_score(*, item: SearchResultItem, total_query_count: int) -> float:
    rank_score = 1.0 / math.sqrt(max(1, item.rank))
    if total_query_count <= 0:
        source_coverage_score = 0.0
    else:
        source_coverage_score = len(item.query_sources) / total_query_count
    return (0.6 * rank_score) + (0.4 * source_coverage_score)


def should_prune_result(
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
    if is_social_post_url(parsed_url.netloc.lower(), lowered_path):
        return True

    result_tokens = tokenize(f"{result.title} {result.snippet}")
    if not (result_tokens & query_tokens) and not (result_tokens & aspect_tokens):
        return True

    return False


def is_social_post_url(domain: str, path: str) -> bool:
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


def normalize_text(value: str) -> str:
    no_tags = HTML_TAG_PATTERN.sub(" ", value)
    return " ".join(unescape(no_tags).split()).strip()


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(value.lower())
        if token and token not in STOPWORDS and len(token) > 1
    }


def merge_query_sources(existing: list[str], incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for query in [*existing, *incoming]:
        if query not in seen:
            seen.add(query)
            merged.append(query)
    return merged


def ordered_unique_queries(queries: list[str]) -> list[str]:
    ordered_unique: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        ordered_unique.append(query)
    return ordered_unique
