from __future__ import annotations

"""Brave LLM Context fetch helper owned by the orchestrator."""

from typing import Protocol
from urllib.parse import urlparse

import httpx
from pydantic import HttpUrl

from backend.app.api_clients import BraveLlmContextClient, HttpBraveLlmContextClient
from backend.app.config import BraveContextRuntimeConfig, load_brave_context_runtime_config
from backend.app.contracts import (
    EvidenceOrigin,
    RetrievedChunk,
    RetrievedSourcesOutput,
    SearchResultItem,
    SearcherOutput,
    UrlSource,
)
from backend.app.helpers.brave_context_cleanup import clean_brave_context_passage_text


class BraveContextFetcher(Protocol):
    def run(self, searcher_output: SearcherOutput) -> RetrievedSourcesOutput:
        """Fetch Brave-context-backed URL sources using the provider-neutral retrieval contract."""


class PlaceholderBraveContextFetcher:
    def run(self, searcher_output: SearcherOutput) -> RetrievedSourcesOutput:
        _ = searcher_output
        return RetrievedSourcesOutput(url_sources=[])


class DefaultBraveContextFetcher:
    def __init__(
        self,
        runtime_config: BraveContextRuntimeConfig | None = None,
        brave_context_client: BraveLlmContextClient | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._brave_context_client = brave_context_client

    def run(self, searcher_output: SearcherOutput) -> RetrievedSourcesOutput:
        config = self._config()
        url_sources: list[UrlSource] = []

        for result in searcher_output.shortlisted_results[: config.max_urls]:
            passages = self._fetch_passages_for_result(
                result=result,
                config=config,
            )
            source_id = _source_id(origin=EvidenceOrigin.BRAVE_LLM, source_url=str(result.url))
            retrieved_chunks = _retrieved_chunks_for_result(
                passages=passages,
                source_id=source_id,
            )
            url_sources.append(
                UrlSource(
                    source_id=source_id,
                    url=result.url,
                    title=result.title,
                    origin=EvidenceOrigin.BRAVE_LLM,
                    metadata={
                        "hostname": result.domain,
                        "fallback": bool(passages) and all(bool(passage["fallback"]) for passage in passages),
                    },
                    chunks=retrieved_chunks,
                )
            )

        return RetrievedSourcesOutput(url_sources=url_sources)

    def _config(self) -> BraveContextRuntimeConfig:
        return self._runtime_config or load_brave_context_runtime_config()

    def _client(self) -> BraveLlmContextClient:
        if self._brave_context_client is not None:
            return self._brave_context_client

        config = self._config()
        if not config.brave_search_api_key:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is missing from the environment")

        self._brave_context_client = HttpBraveLlmContextClient(
            api_key=config.brave_search_api_key,
            endpoint=config.brave_context_endpoint,
            country=config.brave_country,
            search_lang=config.brave_search_lang,
        )
        return self._brave_context_client

    def _fetch_passages_for_result(
        self,
        *,
        result: SearchResultItem,
        config: BraveContextRuntimeConfig,
    ) -> list[dict[str, str | bool]]:
        query = _context_query_for_result(result)
        try:
            fetched_passages = self._client().fetch_context(
                query=query,
                count=3,
                max_urls=3,
                max_tokens=config.max_tokens,
                max_snippets_per_url=config.max_snippets_per_url,
            )
        except httpx.HTTPError:
            fallback_text = _fallback_text_for_result(result, config.max_passage_chars)
            return [{"text": fallback_text, "fallback": True}] if fallback_text else []

        passages = [
            {
                "text": _truncate_passage_text(cleaned_passage_text, config.max_passage_chars),
                "fallback": False,
            }
            for fetched in fetched_passages
            if (
                cleaned_passage_text := clean_brave_context_passage_text(
                    "\n".join(fetched.snippets)
                )
            )
            if _url_matches_result(fetched.source_url, result)
        ]
        if passages:
            return passages

        fallback_text = _fallback_text_for_result(result, config.max_passage_chars)
        return [{"text": fallback_text, "fallback": True}] if fallback_text else []


def build_brave_context_fetcher(
    runtime_config: BraveContextRuntimeConfig | None = None,
    brave_context_client: BraveLlmContextClient | None = None,
) -> BraveContextFetcher:
    config = runtime_config or load_brave_context_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderBraveContextFetcher()
    if config.mode == "brave":
        return DefaultBraveContextFetcher(
            runtime_config=config,
            brave_context_client=brave_context_client,
        )
    raise ValueError(f"Unsupported Brave Context mode: {config.mode}")


def _context_query_for_result(result: SearchResultItem) -> str:
    hostname = urlparse(str(result.url)).netloc
    query_terms = " ".join(
        part.strip()
        for part in [result.title, result.snippet[:160], f"site:{hostname}"]
        if part.strip()
    )
    return query_terms[:400]


def _url_matches_result(source_url: str, result: SearchResultItem) -> bool:
    return source_url == str(result.url)


def _fallback_text_for_result(
    result: SearchResultItem,
    max_passage_chars: int,
) -> str:
    return _truncate_passage_text(result.snippet, max_passage_chars)


def _truncate_passage_text(text: str, max_passage_chars: int) -> str:
    normalized_text = text.strip()
    if max_passage_chars <= 0 or len(normalized_text) <= max_passage_chars:
        return normalized_text

    truncated = normalized_text[:max_passage_chars].rstrip()
    last_space = truncated.rfind(" ")
    if last_space >= max_passage_chars // 2:
        truncated = truncated[:last_space].rstrip()
    return truncated.rstrip(".,;:-")


def _retrieved_chunks_for_result(
    *,
    passages: list[dict[str, str | bool]],
    source_id: str,
) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for index, passage in enumerate(passages):
        text_value = passage.get("text")
        text = text_value.strip() if isinstance(text_value, str) else ""
        if not text:
            continue
        chunks.append(
            RetrievedChunk(
                chunk_id=f"{source_id}#{index}",
                source_id=source_id,
                text=text,
                sequence_index=index,
            )
        )
    return chunks


def _source_id(*, origin: EvidenceOrigin, source_url: str) -> str:
    return f"{origin.value}:{source_url}"
