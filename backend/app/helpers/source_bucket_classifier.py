from __future__ import annotations

"""LLM-backed source bucket classification over Brave metadata."""

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import SearcherRuntimeConfig, load_searcher_runtime_config
from backend.app.contracts import PlannerOutput, SearchResultItem
from backend.app.prompts.source_bucket_prompts import SOURCE_BUCKET_CLASSIFIER_SYSTEM_PROMPT


DEFAULT_SOURCE_BUCKET_MODEL = "gpt-5-mini"
DEFAULT_SOURCE_BUCKET_REASONING_EFFORT = "minimal"

SOURCE_BUCKETS = {
    "official_entity",
    "profile_directory",
    "roundup_list",
    "editorial_reference",
    "transactional_listing",
}


class SourceBucketDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    bucket: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""


class SourceBucketModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[SourceBucketDecision] = Field(default_factory=list)


class SourceBucketClassifier(ABC):
    @abstractmethod
    def classify(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
    ) -> dict[str, SourceBucketDecision]:
        """Classify merged search results into fixed source buckets keyed by URL."""


class PlaceholderSourceBucketClassifier(SourceBucketClassifier):
    def classify(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
    ) -> dict[str, SourceBucketDecision]:
        _ = planner_output
        _ = search_results
        return {}


class DefaultSourceBucketClassifier(SourceBucketClassifier):
    def __init__(
        self,
        *,
        model: str = DEFAULT_SOURCE_BUCKET_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: SearcherRuntimeConfig | None = None,
    ) -> None:
        self._model = model
        self._llm_client = llm_client
        self._runtime_config = runtime_config

    def classify(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
    ) -> dict[str, SourceBucketDecision]:
        if not search_results:
            return {}

        model_output = self._client().parse(
            model=self._model,
            system_prompt=SOURCE_BUCKET_CLASSIFIER_SYSTEM_PROMPT,
            user_content=_build_payload(planner_output=planner_output, search_results=search_results),
            response_model=SourceBucketModelOutput,
            reasoning_effort=DEFAULT_SOURCE_BUCKET_REASONING_EFFORT,
        )
        decisions_by_url: dict[str, SourceBucketDecision] = {}
        for decision in model_output.decisions:
            normalized_url = decision.url.strip()
            if not normalized_url:
                continue
            bucket = decision.bucket.strip()
            if bucket not in SOURCE_BUCKETS:
                bucket = "editorial_reference"
            decisions_by_url[normalized_url] = decision.model_copy(
                update={"url": normalized_url, "bucket": bucket}
            )
        return decisions_by_url

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        config = self._runtime_config or load_searcher_runtime_config()
        if not config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")

        self._llm_client = OpenAiStructuredLlmClient(api_key=config.openai_api_key)
        return self._llm_client


def _build_payload(
    *,
    planner_output: PlannerOutput,
    search_results: list[SearchResultItem],
) -> str:
    payload = {
        "normalized_query": planner_output.normalized_query,
        "base_query": planner_output.base_query,
        "query_rewrites": list(planner_output.initial_query_rewrites),
        "sources": [
            {
                "url": str(result.url),
                "title": result.title,
                "snippet": result.snippet,
                "query_sources": result.query_sources,
                "rank": result.rank,
            }
            for result in search_results
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)
