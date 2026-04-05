from __future__ import annotations

"""Brave LLM Context API adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class BraveLlmContextPassage:
    source_url: str
    title: str
    snippets: list[str]
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)


class BraveLlmContextClient(ABC):
    @abstractmethod
    def fetch_context(
        self,
        *,
        query: str,
        count: int,
        max_urls: int,
        max_tokens: int,
        max_snippets_per_url: int,
    ) -> list[BraveLlmContextPassage]:
        """Fetch pre-extracted Brave context snippets for one query."""


class HttpBraveLlmContextClient(BraveLlmContextClient):
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str,
        country: str,
        search_lang: str,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key
        self._endpoint = endpoint
        self._country = country
        self._search_lang = search_lang
        self._timeout_seconds = timeout_seconds

    def fetch_context(
        self,
        *,
        query: str,
        count: int,
        max_urls: int,
        max_tokens: int,
        max_snippets_per_url: int,
    ) -> list[BraveLlmContextPassage]:
        response = httpx.get(
            self._endpoint,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self._api_key,
            },
            params={
                "q": query,
                "count": count,
                "country": self._country,
                "search_lang": self._search_lang,
                "maximum_number_of_urls": max_urls,
                "maximum_number_of_tokens": max_tokens,
                "maximum_number_of_snippets_per_url": max_snippets_per_url,
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return _parse_context_payload(response.json())


def _parse_context_payload(payload: dict[str, Any]) -> list[BraveLlmContextPassage]:
    grounding = payload.get("grounding", {})
    sources = payload.get("sources", {})
    parsed_passages: list[BraveLlmContextPassage] = []

    for item in _iter_grounding_items(grounding):
        source_url = str(item.get("url", "")).strip()
        if not source_url:
            continue

        source_metadata = sources.get(source_url, {})
        snippets = [
            snippet.strip()
            for snippet in item.get("snippets", [])
            if isinstance(snippet, str) and snippet.strip()
        ]
        if not snippets:
            continue

        parsed_passages.append(
            BraveLlmContextPassage(
                source_url=source_url,
                title=str(item.get("title") or source_metadata.get("title") or "").strip(),
                snippets=snippets,
                metadata={
                    "hostname": source_metadata.get("hostname"),
                    "age": _normalize_age_metadata(source_metadata.get("age")),
                },
            )
        )

    return parsed_passages


def _iter_grounding_items(grounding: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    generic_items = grounding.get("generic", [])
    if isinstance(generic_items, list):
        items.extend(item for item in generic_items if isinstance(item, dict))

    poi_item = grounding.get("poi")
    if isinstance(poi_item, dict):
        items.append(poi_item)

    map_items = grounding.get("map", [])
    if isinstance(map_items, list):
        items.extend(item for item in map_items if isinstance(item, dict))

    return items


def _normalize_age_metadata(raw_age: Any) -> str | None:
    if isinstance(raw_age, list):
        for value in raw_age:
            normalized = str(value).strip()
            if normalized:
                return normalized
    if raw_age is None:
        return None
    normalized = str(raw_age).strip()
    return normalized or None
