from __future__ import annotations

"""Small environment-backed runtime settings loader."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.contracts import DEFAULT_MAX_SHORTLISTED_URLS


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

DEFAULT_PLANNER_MODEL = "gpt-5-mini"
DEFAULT_PLANNER_MODE = "llm"
DEFAULT_EXTRACTOR_LIGHT_MODEL = "gpt-5-mini"
DEFAULT_EXTRACTOR_LIGHT_MODE = "llm"
DEFAULT_EXTRACTOR_MODEL = "gpt-5-mini"
DEFAULT_EXTRACTOR_MODE = "llm"
DEFAULT_ASSESSOR_MODEL = "gpt-5-mini"
DEFAULT_ASSESSOR_MODE = "heuristic"
DEFAULT_SEARCHER_MODE = "brave"
DEFAULT_BRAVE_CONTEXT_MODE = "brave"
DEFAULT_BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_BRAVE_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
DEFAULT_BRAVE_SEARCH_COUNTRY = "us"
DEFAULT_BRAVE_SEARCH_LANG = "en"
DEFAULT_BRAVE_CONTEXT_MAX_URLS = DEFAULT_MAX_SHORTLISTED_URLS
DEFAULT_BRAVE_CONTEXT_MAX_TOKENS = 2048
DEFAULT_BRAVE_CONTEXT_MAX_SNIPPETS_PER_URL = 2
DEFAULT_BRAVE_CONTEXT_MAX_PASSAGE_CHARS = 2048
DEFAULT_BRAVE_INITIAL_COUNT_BY_QUERY_COUNT = {1: 20, 2: 15, 3: 12, 4: 10}
DEFAULT_BRAVE_RETRY_COUNT_BY_QUERY_COUNT = {1: 32, 2: 21, 3: 16, 4: 13}
DEFAULT_SEARCHER_SHORTLIST_CAP = DEFAULT_MAX_SHORTLISTED_URLS
DEFAULT_SEARCHER_WEAK_POOL_THRESHOLD = 8
DEFAULT_JINA_FETCHER_MODE = "jina"
DEFAULT_JINA_READER_BASE_URL = "https://r.jina.ai"
DEFAULT_JINA_TIMEOUT_SECONDS = 30.0
DEFAULT_JINA_MAX_CHUNKS_PER_DOC = 12
DEFAULT_JINA_MAX_CHARS_PER_CHUNK = 1200
DEFAULT_JINA_MIN_CHARS_PER_CHUNK = 400
ENV_BRAVE_SEARCH_API_KEY = "BRAVE_SEARCH_API_KEY"
ENV_ASSESSOR_MODE = "ASSESSOR_MODE"
ENV_ASSESSOR_MODEL = "ASSESSOR_MODEL"
ENV_BRAVE_CONTEXT_MODE = "BRAVE_CONTEXT_MODE"
ENV_EXTRACTOR_LIGHT_MODE = "EXTRACTOR_LIGHT_MODE"
ENV_EXTRACTOR_LIGHT_MODEL = "EXTRACTOR_LIGHT_MODEL"
ENV_EXTRACTOR_MODE = "EXTRACTOR_MODE"
ENV_EXTRACTOR_MODEL = "EXTRACTOR_MODEL"
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
class ExtractorLightRuntimeConfig:
    model: str = DEFAULT_EXTRACTOR_LIGHT_MODEL
    mode: str = DEFAULT_EXTRACTOR_LIGHT_MODE
    openai_api_key: str | None = None


@dataclass(frozen=True)
class ExtractorRuntimeConfig:
    model: str = DEFAULT_EXTRACTOR_MODEL
    mode: str = DEFAULT_EXTRACTOR_MODE
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


@dataclass(frozen=True)
class BraveContextRuntimeConfig:
    mode: str = DEFAULT_BRAVE_CONTEXT_MODE
    brave_search_api_key: str | None = None
    brave_context_endpoint: str = DEFAULT_BRAVE_CONTEXT_ENDPOINT
    brave_country: str = DEFAULT_BRAVE_SEARCH_COUNTRY
    brave_search_lang: str = DEFAULT_BRAVE_SEARCH_LANG
    max_urls: int = DEFAULT_BRAVE_CONTEXT_MAX_URLS
    max_tokens: int = DEFAULT_BRAVE_CONTEXT_MAX_TOKENS
    max_snippets_per_url: int = DEFAULT_BRAVE_CONTEXT_MAX_SNIPPETS_PER_URL
    max_passage_chars: int = DEFAULT_BRAVE_CONTEXT_MAX_PASSAGE_CHARS


@dataclass(frozen=True)
class AssessorRuntimeConfig:
    model: str = DEFAULT_ASSESSOR_MODEL
    mode: str = DEFAULT_ASSESSOR_MODE
    openai_api_key: str | None = None


@dataclass(frozen=True)
class JinaFetcherRuntimeConfig:
    mode: str = DEFAULT_JINA_FETCHER_MODE
    jina_api_key: str | None = None
    reader_base_url: str = DEFAULT_JINA_READER_BASE_URL
    timeout_seconds: float = DEFAULT_JINA_TIMEOUT_SECONDS
    max_chunks_per_doc: int = DEFAULT_JINA_MAX_CHUNKS_PER_DOC
    max_chars_per_chunk: int = DEFAULT_JINA_MAX_CHARS_PER_CHUNK
    min_chars_per_chunk: int = DEFAULT_JINA_MIN_CHARS_PER_CHUNK


def _load_env_file(env_path: Path = DEFAULT_ENV_PATH) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_planner_runtime_config(env_path: Path = DEFAULT_ENV_PATH) -> PlannerRuntimeConfig:
    _load_env_file(env_path)
    return PlannerRuntimeConfig(
        model=os.getenv(ENV_PLANNER_MODEL, DEFAULT_PLANNER_MODEL).strip() or DEFAULT_PLANNER_MODEL,
        mode=os.getenv(ENV_PLANNER_MODE, DEFAULT_PLANNER_MODE).strip() or DEFAULT_PLANNER_MODE,
        openai_api_key=os.getenv(ENV_OPENAI_API_KEY),
    )


def load_searcher_runtime_config(env_path: Path = DEFAULT_ENV_PATH) -> SearcherRuntimeConfig:
    _load_env_file(env_path)
    return SearcherRuntimeConfig(
        mode=os.getenv(ENV_SEARCHER_MODE, DEFAULT_SEARCHER_MODE).strip() or DEFAULT_SEARCHER_MODE,
        brave_search_api_key=os.getenv(ENV_BRAVE_SEARCH_API_KEY),
    )


def load_extractor_light_runtime_config(
    env_path: Path = DEFAULT_ENV_PATH,
) -> ExtractorLightRuntimeConfig:
    _load_env_file(env_path)
    return ExtractorLightRuntimeConfig(
        model=os.getenv(ENV_EXTRACTOR_LIGHT_MODEL, DEFAULT_EXTRACTOR_LIGHT_MODEL).strip()
        or DEFAULT_EXTRACTOR_LIGHT_MODEL,
        mode=os.getenv(ENV_EXTRACTOR_LIGHT_MODE, DEFAULT_EXTRACTOR_LIGHT_MODE).strip()
        or DEFAULT_EXTRACTOR_LIGHT_MODE,
        openai_api_key=os.getenv(ENV_OPENAI_API_KEY),
    )


def load_extractor_runtime_config(
    env_path: Path = DEFAULT_ENV_PATH,
) -> ExtractorRuntimeConfig:
    _load_env_file(env_path)
    return ExtractorRuntimeConfig(
        model=os.getenv(ENV_EXTRACTOR_MODEL, DEFAULT_EXTRACTOR_MODEL).strip()
        or DEFAULT_EXTRACTOR_MODEL,
        mode=os.getenv(ENV_EXTRACTOR_MODE, DEFAULT_EXTRACTOR_MODE).strip()
        or DEFAULT_EXTRACTOR_MODE,
        openai_api_key=os.getenv(ENV_OPENAI_API_KEY),
    )


def load_brave_context_runtime_config(
    env_path: Path = DEFAULT_ENV_PATH,
) -> BraveContextRuntimeConfig:
    _load_env_file(env_path)
    return BraveContextRuntimeConfig(
        mode=os.getenv(ENV_BRAVE_CONTEXT_MODE, DEFAULT_BRAVE_CONTEXT_MODE).strip()
        or DEFAULT_BRAVE_CONTEXT_MODE,
        brave_search_api_key=os.getenv(ENV_BRAVE_SEARCH_API_KEY),
    )


def load_assessor_runtime_config(env_path: Path = DEFAULT_ENV_PATH) -> AssessorRuntimeConfig:
    _load_env_file(env_path)
    return AssessorRuntimeConfig(
        model=os.getenv(ENV_ASSESSOR_MODEL, DEFAULT_ASSESSOR_MODEL).strip()
        or DEFAULT_ASSESSOR_MODEL,
        mode=os.getenv(ENV_ASSESSOR_MODE, DEFAULT_ASSESSOR_MODE).strip()
        or DEFAULT_ASSESSOR_MODE,
        openai_api_key=os.getenv(ENV_OPENAI_API_KEY),
    )


def load_jina_fetcher_runtime_config(
    env_path: Path = DEFAULT_ENV_PATH,
) -> JinaFetcherRuntimeConfig:
    _load_env_file(env_path)
    return JinaFetcherRuntimeConfig(
        mode=os.getenv(ENV_JINA_FETCHER_MODE, DEFAULT_JINA_FETCHER_MODE).strip()
        or DEFAULT_JINA_FETCHER_MODE,
        jina_api_key=os.getenv(ENV_JINA_API_KEY),
    )
