from __future__ import annotations

"""Jina Reader API adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urljoin

import httpx


@dataclass(frozen=True)
class JinaReaderDocument:
    url: str
    title: str
    text: str


class JinaReaderClient(ABC):
    @abstractmethod
    def fetch_url(self, *, url: str) -> JinaReaderDocument:
        """Fetch one URL through Jina Reader and return extracted text."""


class HttpJinaReaderClient(JinaReaderClient):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def fetch_url(self, *, url: str) -> JinaReaderDocument:
        headers = {"Accept": "text/plain"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = httpx.get(
            urljoin(self._base_url, url),
            headers=headers,
            timeout=self._timeout_seconds,
            follow_redirects=True,
        )
        response.raise_for_status()

        text = response.text.strip()
        return JinaReaderDocument(
            url=url,
            title=_extract_title(text=text, fallback_url=url),
            text=text,
        )


def _extract_title(*, text: str, fallback_url: str) -> str:
    for line in text.splitlines():
        normalized = line.strip()
        if normalized.startswith("Title:"):
            title = normalized.removeprefix("Title:").strip()
            if title:
                return title
        if normalized:
            return normalized[:200]
    return fallback_url
