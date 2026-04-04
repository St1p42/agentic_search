from __future__ import annotations

"""Small environment-backed runtime settings loader."""

import os
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

DEFAULT_PLANNER_MODEL = "gpt-5-mini"
DEFAULT_PLANNER_MODE = "llm"
DEFAULT_ASSESSOR_MODEL = "gpt-5-mini"
DEFAULT_ASSESSOR_MODE = "llm"
DEFAULT_SEARCHER_MODE = "brave"
DEFAULT_BRAVE_CONTEXT_MODE = "brave"
DEFAULT_BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_BRAVE_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
DEFAULT_BRAVE_SEARCH_COUNTRY = "us"
DEFAULT_BRAVE_SEARCH_LANG = "en"
DEFAULT_BRAVE_CONTEXT_MAX_URLS = 15
DEFAULT_BRAVE_CONTEXT_MAX_TOKENS = 8192
DEFAULT_BRAVE_CONTEXT_MAX_SNIPPETS_PER_URL = 8
DEFAULT_BRAVE_INITIAL_COUNT_BY_QUERY_COUNT = {1: 20, 2: 15, 3: 12, 4: 10}
DEFAULT_BRAVE_RETRY_COUNT_BY_QUERY_COUNT = {1: 32, 2: 21, 3: 16, 4: 13}
DEFAULT_SEARCHER_SHORTLIST_CAP = 15
DEFAULT_SEARCHER_WEAK_POOL_THRESHOLD = 8
DEFAULT_JINA_FETCHER_MODE = "jina"
DEFAULT_JINA_READER_BASE_URL = "https://r.jina.ai"
DEFAULT_JINA_TIMEOUT_SECONDS = 30.0
DEFAULT_JINA_MAX_CHUNKS_PER_DOC = 6
DEFAULT_JINA_MAX_CHARS_PER_CHUNK = 2500
ENV_BRAVE_SEARCH_API_KEY = "BRAVE_SEARCH_API_KEY"
ENV_ASSESSOR_MODE = "ASSESSOR_MODE"
ENV_ASSESSOR_MODEL = "ASSESSOR_MODEL"
ENV_BRAVE_CONTEXT_MODE = "BRAVE_CONTEXT_MODE"
ENV_JINA_API_KEY = "JINA_API_KEY"
ENV_JINA_FETCHER_MODE = "JINA_FETCHER_MODE"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_PLANNER_MODE = "PLANNER_MODE"
ENV_PLANNER_MODEL = "PLANNER_MODEL"
ENV_SEARCHER_MODE = "SEARCHER_MODE"


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    model: str = DEFAULT_PLANNER_MODEL
    mode: str = DEFAULT_PLANNER_MODE
    openai_api_key: str | None = None


@dataclass(frozen=True)
class SearcherRuntimeConfig:
    mode: str = DEFAULT_SEARCHER_MODE
    brave_search_api_key: str | None = None
    brave_search_endpoint: str = DEFAULT_BRAVE_SEARCH_ENDPOINT
    brave_country: str = DEFAULT_BRAVE_SEARCH_COUNTRY
    brave_search_lang: str = DEFAULT_BRAVE_SEARCH_LANG
    initial_count_by_query_count: dict[int, int] = field(
        default_factory=lambda: dict(DEFAULT_BRAVE_INITIAL_COUNT_BY_QUERY_COUNT)
    )
    retry_count_by_query_count: dict[int, int] = field(
        default_factory=lambda: dict(DEFAULT_BRAVE_RETRY_COUNT_BY_QUERY_COUNT)
    )
    shortlist_cap: int = DEFAULT_SEARCHER_SHORTLIST_CAP
    weak_pool_threshold: int = DEFAULT_SEARCHER_WEAK_POOL_THRESHOLD

