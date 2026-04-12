from __future__ import annotations

"""ExtractorLight stage interface plus placeholder and LLM-backed implementations."""

import re
import unicodedata
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import (
    DEFAULT_EXTRACTOR_LIGHT_MODEL,
    ExtractorLightRuntimeConfig,
    load_extractor_light_runtime_config,
)
from backend.app.contracts import BraveContextOutput, ExtractorLightOutput, PlannerOutput
from backend.app.prompts import EXTRACTOR_LIGHT_SYSTEM_PROMPT
from backend.app.stages.entity_name_filter import EntityNameFilter


MIN_CANDIDATE_NAME_CHARS = 2
MAX_CANDIDATE_NAME_CHARS = 80


class ExtractorLightStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        """Extract candidate names only and map those names to mentioning URLs."""


class PlaceholderExtractorLightStage:
    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        _ = planner_output
        _ = brave_context_output
        return ExtractorLightOutput(
            candidate_names=[],
            name_to_source_urls={},
            mention_counts={},
        )


class ExtractorLightModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_names: list[str] = Field(default_factory=list)


class LlmExtractorLightStage:
    def __init__(
        self,
        model: str = DEFAULT_EXTRACTOR_LIGHT_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: ExtractorLightRuntimeConfig | None = None,
        entity_name_filter: EntityNameFilter | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = "minimal"
        self._llm_client = llm_client
        self._runtime_config = runtime_config
        self._entity_name_filter = entity_name_filter or EntityNameFilter()

    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        if not brave_context_output.passages_by_url:
            return ExtractorLightOutput(
                candidate_names=[],
                name_to_source_urls={},
                mention_counts={},
            )

        model_output = self._client().parse(
            model=self.model,
            system_prompt=EXTRACTOR_LIGHT_SYSTEM_PROMPT,
            user_content=_build_extractor_light_payload(
                planner_output=planner_output,
                brave_context_output=brave_context_output,
            ),
            response_model=ExtractorLightModelOutput,
            reasoning_effort=self.reasoning_effort,
        )
        return _to_extractor_light_output(
            planner_output=planner_output,
            model_output=model_output,
            brave_context_output=brave_context_output,
            entity_name_filter=self._entity_name_filter,
        )

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        extractor_light_config = self._runtime_config or load_extractor_light_runtime_config()
        if not extractor_light_config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")

        self.model = self.model or extractor_light_config.model
        self._llm_client = OpenAiStructuredLlmClient(api_key=extractor_light_config.openai_api_key)
        return self._llm_client


def build_extractor_light_stage(
    runtime_config: ExtractorLightRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> ExtractorLightStage:
    config = runtime_config or load_extractor_light_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderExtractorLightStage()
    if config.mode == "llm":
        return LlmExtractorLightStage(
            model=config.model,
            llm_client=llm_client,
            runtime_config=config,
        )
    raise ValueError(f"Unsupported extractor_light mode: {config.mode}")


def _build_extractor_light_payload(
    *,
    planner_output: PlannerOutput,
    brave_context_output: BraveContextOutput,
) -> str:
    payload_lines = [f"entity_type: {planner_output.entity_type}", "passages:"]
    passage_index = 1

    for passages in brave_context_output.passages_by_url.values():
        for passage in passages:
            passage_text = " ".join(passage.passage_text.split()).strip()
            if not passage_text:
                continue
            payload_lines.append(f"[p{passage_index}] {passage_text}")
            passage_index += 1

    return "\n".join(payload_lines)


def _to_extractor_light_output(
    *,
    planner_output: PlannerOutput,
    model_output: ExtractorLightModelOutput,
    brave_context_output: BraveContextOutput,
    entity_name_filter: EntityNameFilter,
) -> ExtractorLightOutput:
    candidate_names = _normalize_candidate_names(model_output.candidate_names)
    name_to_source_urls: dict[str, list[HttpUrl]] = {}
    mention_counts: dict[str, int] = {}
    passage_texts_by_url = {
        source_url: "\n".join(
            passage.passage_text for passage in passages if passage.passage_text.strip()
        )
        for source_url, passages in brave_context_output.passages_by_url.items()
    }

    for candidate_name in candidate_names:
        source_urls = _find_source_urls_for_name(
            candidate_name=candidate_name,
            passage_texts_by_url=passage_texts_by_url,
        )
        mention_count = _count_name_mentions(
            candidate_name=candidate_name,
            passage_texts_by_url=passage_texts_by_url,
        )
        if not _should_keep_candidate_name(candidate_name=candidate_name):
            continue
        name_to_source_urls[candidate_name] = source_urls
        mention_counts[candidate_name] = mention_count

    candidate_names_out, name_to_source_urls, mention_counts = _dedupe_subset_variants(
        name_to_source_urls=name_to_source_urls,
        mention_counts=mention_counts,
    )
    candidate_names_out, name_to_source_urls, mention_counts = entity_name_filter.filter(
        planner_output=planner_output,
        candidate_names=candidate_names_out,
        name_to_source_urls=name_to_source_urls,
        mention_counts=mention_counts,
    )

    return ExtractorLightOutput(
        candidate_names=candidate_names_out,
        name_to_source_urls=name_to_source_urls,
        mention_counts=mention_counts,
    )


def _normalize_candidate_names(candidate_names: list[str]) -> list[str]:
    normalized_names: list[str] = []
    seen_names: set[str] = set()
    for candidate_name in candidate_names:
        normalized_name = _normalize_name(candidate_name)
        dedupe_key = normalized_name.casefold()
        if not normalized_name or dedupe_key in seen_names:
            continue
        seen_names.add(dedupe_key)
        normalized_names.append(normalized_name)
    return normalized_names


def _normalize_name(name: str) -> str:
    return " ".join(name.split()).strip()


def _find_source_urls_for_name(
    *,
    candidate_name: str,
    passage_texts_by_url: dict[HttpUrl, str],
) -> list[HttpUrl]:
    name_pattern = _candidate_name_pattern(candidate_name)
    if name_pattern is None:
        return []
    return [
        source_url
        for source_url, passage_text in passage_texts_by_url.items()
        if name_pattern.search(_normalize_match_text(passage_text))
    ]


def _count_name_mentions(
    *,
    candidate_name: str,
    passage_texts_by_url: dict[HttpUrl, str],
) -> int:
    name_pattern = _candidate_name_pattern(candidate_name)
    if name_pattern is None:
        return 0
    mention_count = sum(
        len(name_pattern.findall(_normalize_match_text(passage_text)))
        for passage_text in passage_texts_by_url.values()
    )
    return mention_count


def _dedupe_urls(source_urls: list[HttpUrl]) -> list[HttpUrl]:
    deduped_urls: list[HttpUrl] = []
    seen_urls: set[str] = set()
    for source_url in source_urls:
        dedupe_key = str(source_url)
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        deduped_urls.append(source_url)
    return deduped_urls


def _candidate_name_pattern(candidate_name: str) -> re.Pattern[str] | None:
    normalized_name = _normalize_match_text(candidate_name)
    if not normalized_name:
        return None
    escaped_name = re.escape(normalized_name)
    return re.compile(rf"(?<!\w){escaped_name}(?:'s)?(?!\w)", re.IGNORECASE)


def _normalize_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.casefold())
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("`", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _should_keep_candidate_name(
    *,
    candidate_name: str,
) -> bool:
    normalized_name = candidate_name.strip()
    if len(normalized_name) < MIN_CANDIDATE_NAME_CHARS:
        return False
    if len(normalized_name) > MAX_CANDIDATE_NAME_CHARS:
        return False
    return True


def _dedupe_subset_variants(
    *,
    name_to_source_urls: dict[str, list[HttpUrl]],
    mention_counts: dict[str, int],
) -> tuple[list[str], dict[str, list[HttpUrl]], dict[str, int]]:
    candidate_names = list(name_to_source_urls.keys())
    names_to_drop: set[str] = set()

    for candidate_name in candidate_names:
        if candidate_name in names_to_drop:
            continue
        candidate_key = _normalized_comparison_key(candidate_name)
        candidate_urls = {str(url) for url in name_to_source_urls[candidate_name]}

        for other_name in candidate_names:
            if candidate_name == other_name or other_name in names_to_drop:
                continue

            other_key = _normalized_comparison_key(other_name)
            if not candidate_key or not other_key or candidate_key == other_key:
                continue
            if not _is_full_subset_name(candidate_key, other_key):
                continue

            other_urls = {str(url) for url in name_to_source_urls[other_name]}
            if not (candidate_urls & other_urls):
                continue

            candidate_url_count = len(candidate_urls)
            other_url_count = len(other_urls)
            if candidate_url_count < other_url_count:
                names_to_drop.add(candidate_name)
                break
            if candidate_url_count > other_url_count:
                names_to_drop.add(other_name)
                continue

            if len(candidate_key) < len(other_key):
                names_to_drop.add(candidate_name)
                break
            if len(other_key) < len(candidate_key):
                names_to_drop.add(other_name)

    deduped_candidate_names = [
        candidate_name for candidate_name in candidate_names if candidate_name not in names_to_drop
    ]
    deduped_name_to_source_urls = {
        candidate_name: name_to_source_urls[candidate_name]
        for candidate_name in deduped_candidate_names
    }
    deduped_mention_counts = {
        candidate_name: mention_counts[candidate_name] for candidate_name in deduped_candidate_names
    }
    return deduped_candidate_names, deduped_name_to_source_urls, deduped_mention_counts


def _normalized_comparison_key(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", name.casefold())
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("`", "'")
    normalized = normalized.strip(" \t\n\r\"'“”‘’.,;:!?()[]{}<>")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _is_full_subset_name(left: str, right: str) -> bool:
    left_tokens = left.split()
    right_tokens = right.split()
    if not left_tokens or not right_tokens or len(left_tokens) >= len(right_tokens):
        return False
    for start_index in range(len(right_tokens) - len(left_tokens) + 1):
        if right_tokens[start_index : start_index + len(left_tokens)] == left_tokens:
            return True
    return False
