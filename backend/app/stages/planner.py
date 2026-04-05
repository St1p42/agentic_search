from __future__ import annotations

"""Planner stage interface plus deterministic and LLM-backed implementations."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import (
    DEFAULT_PLANNER_MODEL,
    PlannerRuntimeConfig,
    load_planner_runtime_config,
)
from backend.app.contracts import PlannerOutput
from backend.app.prompts import PLANNER_SYSTEM_PROMPT


class PlannerStage(Protocol):
    def run(self, query: str) -> PlannerOutput:
        """Return a query plan for downstream retrieval and extraction."""


class PlannerModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str = "unknown_entity"
    query_mode: str = "topic_entity_discovery"
    schema_columns: list[str] = Field(default_factory=list)
    core_aspects: list[str] = Field(default_factory=list)
    base_query: str = ""
    initial_query_rewrites: list[str] = Field(default_factory=list)
    is_topic_query: bool = True
    normalized_query: str = ""
    normalization_note: str | None = None
    error: bool = False
    error_message: str | None = None


class LlmPlannerStage:
    def __init__(
        self,
        model: str = DEFAULT_PLANNER_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: PlannerRuntimeConfig | None = None,
    ) -> None:
        self.model = model
        self._llm_client = llm_client
        self._runtime_config = runtime_config

    def run(self, query: str) -> PlannerOutput:
        normalized_raw_query = " ".join(query.split())
        if not normalized_raw_query:
            return self._planner_error(
                normalized_query="",
                base_query="",
                error_message="Query is empty. Please provide a topic describing entities to discover.",
            )

        try:
            model_output = self._client().parse(
                model=self.model,
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_content=normalized_raw_query,
                response_model=PlannerModelOutput,
            )
        except RuntimeError as exc:
            return self._planner_error(
                normalized_query=normalized_raw_query,
                base_query=normalized_raw_query,
                error_message=str(exc),
            )

        return self._to_planner_output(model_output=model_output, raw_query=normalized_raw_query)

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        planner_config = self._runtime_config or load_planner_runtime_config()
        if not planner_config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")

        self.model = self.model or planner_config.model
        self._llm_client = OpenAiStructuredLlmClient(api_key=planner_config.openai_api_key)
        return self._llm_client

    def _to_planner_output(
        self,
        *,
        model_output: PlannerModelOutput,
        raw_query: str,
    ) -> PlannerOutput:
        normalized_query = " ".join((model_output.normalized_query or raw_query).split())
        base_query = " ".join((model_output.base_query or normalized_query or raw_query).split())

        if model_output.error:
            return self._planner_error(
                normalized_query=normalized_query,
                base_query=base_query,
                error_message=model_output.error_message
                or "This query is not a supported entity-discovery topic.",
                normalization_note=model_output.normalization_note,
                is_topic_query=model_output.is_topic_query,
                query_mode=model_output.query_mode or "invalid_query",
                entity_type=model_output.entity_type or "unknown_entity",
            )

        return PlannerOutput(
            entity_type=(model_output.entity_type or "entity").strip() or "entity",
            query_mode=(model_output.query_mode or "topic_entity_discovery").strip()
            or "topic_entity_discovery",
            schema_columns=self._normalize_schema_columns(
                model_output.schema_columns,
            ),
            core_aspects=self._normalize_unique_list(
                model_output.core_aspects,
                fallback=["category"],
                min_length=1,
                max_length=5,
            ),
            base_query=base_query,
            initial_query_rewrites=self._normalize_unique_list(
                model_output.initial_query_rewrites,
                fallback=[],
                min_length=0,
                max_length=3,
                blocked_values={base_query.lower(), normalized_query.lower()},
            ),
            is_topic_query=model_output.is_topic_query,
            normalized_query=normalized_query,
            normalization_note=model_output.normalization_note,
            error=False,
            error_message=None,
        )

    @staticmethod
    def _normalize_unique_list(
        values: list[str],
        *,
        fallback: list[str],
        min_length: int,
        max_length: int,
        blocked_values: set[str] | None = None,
    ) -> list[str]:
        blocked_values = blocked_values or set()
        normalized_values: list[str] = []
        seen_values: set[str] = set()

        for value in values:
            normalized = " ".join(value.split()).strip()
            dedupe_key = normalized.lower()
            if not normalized or dedupe_key in seen_values or dedupe_key in blocked_values:
                continue
            seen_values.add(dedupe_key)
            normalized_values.append(normalized)
            if len(normalized_values) >= max_length:
                break

        for value in fallback:
            if len(normalized_values) >= min_length:
                break
            normalized = " ".join(value.split()).strip()
            dedupe_key = normalized.lower()
            if not normalized or dedupe_key in seen_values or dedupe_key in blocked_values:
                continue
            seen_values.add(dedupe_key)
            normalized_values.append(normalized)

        while len(normalized_values) < min_length:
            filler = f"field_{len(normalized_values) + 1}"
            if filler not in normalized_values:
                normalized_values.append(filler)

        return normalized_values[:max_length]

    @classmethod
    def _normalize_schema_columns(cls, values: list[str]) -> list[str]:
        schema_columns = cls._normalize_unique_list(
            values,
            fallback=["name", "website", "location", "category"],
            min_length=4,
            max_length=6,
        )
        if "name" in {column.lower() for column in schema_columns}:
            return schema_columns

        if len(schema_columns) >= 6:
            schema_columns = schema_columns[:5]
        return ["name", *schema_columns]

    @staticmethod
    def _planner_error(
        *,
        normalized_query: str,
        base_query: str,
        error_message: str,
        normalization_note: str | None = None,
        is_topic_query: bool = False,
        query_mode: str = "invalid_query",
        entity_type: str = "unknown_entity",
    ) -> PlannerOutput:
        return PlannerOutput(
            entity_type=entity_type or "unknown_entity",
            query_mode=query_mode or "invalid_query",
            schema_columns=["name", "website", "location", "category"],
            core_aspects=["category"],
            base_query=base_query,
            initial_query_rewrites=[],
            is_topic_query=is_topic_query,
            normalized_query=normalized_query,
            normalization_note=normalization_note,
            error=True,
            error_message=error_message,
        )


class PlaceholderPlannerStage:
    def run(self, query: str) -> PlannerOutput:
        return PlannerOutput(
            entity_type="unknown_entity",
            query_mode="general_web",
            schema_columns=["name", "website", "location", "category"],
            core_aspects=["category"],
            base_query=query,
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query=query,
        )


def build_planner_stage(
    runtime_config: PlannerRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> PlannerStage:
    config = runtime_config or load_planner_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderPlannerStage()
    if config.mode == "llm":
        return LlmPlannerStage(
            model=config.model,
            llm_client=llm_client,
            runtime_config=config,
        )
    raise ValueError(f"Unsupported planner mode: {config.mode}")
