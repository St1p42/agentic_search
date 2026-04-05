from __future__ import annotations

"""Brave Search API adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx


@dataclass(frozen=True)
class BraveWebResult:
    url: str
    title: str
    snippet: str
    domain: str
    rank: int
    result_type: str | None
    provider_metadata: dict[str, str | int | float | bool | None]


class BraveSearchClient(ABC):
    @abstractmethod
    def search_web(self, *, query: str, count: int) -> list[BraveWebResult]:
        """Run one Brave Web Search query and return ranked results."""


class HttpBraveSearchClient(BraveSearchClient):
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

    def search_web(self, *, query: str, count: int) -> list[BraveWebResult]:
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
            },
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return _parse_web_results(payload)


def _parse_web_results(payload: dict[str, Any]) -> list[BraveWebResult]:
    web_results = payload.get("web", {}).get("results", [])
    parsed_results: list[BraveWebResult] = []

    for rank, item in enumerate(web_results, start=1):
        url = str(item.get("url", "")).strip()
        if not url:
            continue

        domain = str(item.get("profile", {}).get("long_name", "")).strip()
        if not domain:
            domain = urlparse(url).netloc

        parsed_results.append(
            BraveWebResult(
                url=url,
                title=str(item.get("title", "")).strip(),
                snippet=str(item.get("description", "")).strip(),
                domain=domain,
                rank=rank,
                result_type=str(item.get("type", "")).strip() or None,
                provider_metadata={
                    "source": "brave_web_search",
                    "family_friendly": item.get("family_friendly"),
                    "is_source_local": item.get("is_source_local"),
                    "is_source_both": item.get("is_source_both"),
                    "language": item.get("language"),
                },
            )
        )

    return parsed_results
