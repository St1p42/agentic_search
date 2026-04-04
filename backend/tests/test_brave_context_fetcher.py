from __future__ import annotations

from pydantic import HttpUrl

from backend.app.api_clients import BraveLlmContextClient, BraveLlmContextPassage
from backend.app.config import BraveContextRuntimeConfig
from backend.app.contracts import SearchResultItem, SearcherOutput
from backend.app.helpers.brave_context_fetcher import DefaultBraveContextFetcher


class FakeBraveContextClient(BraveLlmContextClient):
    def __init__(
        self,
        passages_by_query: dict[str, list[BraveLlmContextPassage]],
    ) -> None:
        self._passages_by_query = passages_by_query
        self.calls: list[str] = []

    def fetch_context(
        self,
        *,
        query: str,
        count: int,
        max_urls: int,
        max_tokens: int,
        max_snippets_per_url: int,
    ) -> list[BraveLlmContextPassage]:
        _ = count
        _ = max_urls
        _ = max_tokens
        _ = max_snippets_per_url
        self.calls.append(query)
        return self._passages_by_query.get(query, [])


def _search_result(
    *,
    url: str,
    title: str,
    snippet: str,
    domain: str,
    rank: int = 1,
) -> SearchResultItem:
    return SearchResultItem(
        url=HttpUrl(url),
        title=title,
        snippet=snippet,
        domain=domain,
        rank=rank,
        query_sources=["AI startups in healthcare"],
        result_type="search_result",
        provider_metadata={"source": "brave_web_search"},
    )


def test_default_brave_context_fetcher_returns_passages_and_falls_back_to_snippet() -> None:
    matching_result = _search_result(
        url="https://acmehealth.com/about",
        title="Acme Health",
        snippet="Acme Health builds clinical AI tools",
        domain="acmehealth.com",
    )
    fallback_result = _search_result(
        url="https://beta.ai",
        title="Beta AI",
        snippet="Beta AI develops healthcare copilots",
        domain="beta.ai",
        rank=2,
    )
    expected_query = "Acme Health Acme Health builds clinical AI tools site:acmehealth.com"
    fake_client = FakeBraveContextClient(
        passages_by_query={
            expected_query: [
                BraveLlmContextPassage(
                    source_url="https://acmehealth.com/team",
                    title="Team",
                    snippets=["Different same-host page should be ignored."],
                    metadata={"hostname": "acmehealth.com"},
                ),
                BraveLlmContextPassage(
                    source_url="https://acmehealth.com/about",
                    title="About Acme",
                    snippets=["Acme Health is a clinical AI company."],
                    metadata={"hostname": "acmehealth.com"},
                )
            ]
        }
    )
    fetcher = DefaultBraveContextFetcher(
        runtime_config=BraveContextRuntimeConfig(
            mode="brave",
            brave_search_api_key="fake-key",
            max_urls=5,
            max_tokens=4096,
            max_snippets_per_url=5,
        ),
        brave_context_client=fake_client,
    )

    output = fetcher.run(
        SearcherOutput(
            executed_queries=["AI startups in healthcare"],
            raw_results=[matching_result, fallback_result],
            shortlisted_results=[matching_result, fallback_result],
        )
    )

    assert output.passages_by_url[HttpUrl("https://acmehealth.com/about")][0].passage_text == (
        "Acme Health is a clinical AI company."
    )
    assert len(output.passages_by_url[HttpUrl("https://acmehealth.com/about")]) == 1
    assert output.passages_by_url[HttpUrl("https://beta.ai")][0].passage_text == (
        "Beta AI develops healthcare copilots"
    )
    assert output.passages_by_url[HttpUrl("https://beta.ai")][0].metadata["fallback"] is True
    assert fake_client.calls[0] == expected_query


def test_default_brave_context_fetcher_cleans_passage_text_and_falls_back_if_only_junk() -> None:
    cleaned_result = _search_result(
        url="https://acmehealth.com/about",
        title="Acme Health",
        snippet="Acme Health builds clinical AI tools",
        domain="acmehealth.com",
    )
    junk_result = _search_result(
        url="https://beta.ai",
        title="Beta AI",
        snippet="Beta AI develops healthcare copilots",
        domain="beta.ai",
        rank=2,
    )
    fake_client = FakeBraveContextClient(
        passages_by_query={
            "Acme Health Acme Health builds clinical AI tools site:acmehealth.com": [
                BraveLlmContextPassage(
                    source_url="https://acmehealth.com/about",
                    title="About Acme",
                    snippets=[
                        '{"@type": "Article", "headline": "Acme"}',
                        "*[Image: hero]*  |",
                        "| --- | --- |",
                        "|",
                        "**Read more below**",
                        "Show Pros &amp; Cons",
                        "Best Phone Overall",
                        "Acme Health builds clinical AI tools.",
                    ],
                    metadata={"hostname": "acmehealth.com"},
                )
            ],
            "Beta AI Beta AI develops healthcare copilots site:beta.ai": [
                BraveLlmContextPassage(
                    source_url="https://beta.ai",
                    title="Beta AI",
                    snippets=[
                        '{"@type": "Article", "headline": "Beta"}',
                        "*[Image]*",
                        "Show Pros & Cons",
                    ],
                    metadata={"hostname": "beta.ai"},
                )
            ],
        }
    )
    fetcher = DefaultBraveContextFetcher(
        runtime_config=BraveContextRuntimeConfig(
            mode="brave",
            brave_search_api_key="fake-key",
            max_urls=5,
            max_tokens=2048,
            max_snippets_per_url=2,
        ),
        brave_context_client=fake_client,
    )

    output = fetcher.run(
        SearcherOutput(
            executed_queries=["AI startups in healthcare"],
            raw_results=[cleaned_result, junk_result],
            shortlisted_results=[cleaned_result, junk_result],
        )
    )

    assert output.passages_by_url[HttpUrl("https://acmehealth.com/about")][0].passage_text == (
        "Best Phone Overall\nAcme Health builds clinical AI tools."
    )
    assert output.passages_by_url[HttpUrl("https://beta.ai")][0].passage_text == (
        "Beta AI develops healthcare copilots"
    )
    assert output.passages_by_url[HttpUrl("https://beta.ai")][0].metadata["fallback"] is True
