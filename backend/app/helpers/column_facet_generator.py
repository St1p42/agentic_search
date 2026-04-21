from __future__ import annotations

import json
from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import load_planner_runtime_config
from backend.app.prompts.column_facet_prompts import COLUMN_FACET_GENERATOR_SYSTEM_PROMPT


DEFAULT_COLUMN_FACET_GENERATOR_MODEL = "gpt-5-mini"
DEFAULT_COLUMN_FACET_REASONING_EFFORT = "minimal"


class ColumnFacet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    facet_terms: list[str] = Field(default_factory=list, min_length=1, max_length=4)


class ColumnFacetOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facets: list[ColumnFacet] = Field(default_factory=list)


class ColumnFacetGenerator(ABC):
    @abstractmethod
    def generate(
        self,
        *,
        normalized_query: str,
        base_query: str,
        sparse_columns: list[str],
    ) -> ColumnFacetOutput:
        """Generate retrieval-oriented facet terms for sparse columns."""


class PlaceholderColumnFacetGenerator(ColumnFacetGenerator):
    def generate(
        self,
        *,
        normalized_query: str,
        base_query: str,
        sparse_columns: list[str],
    ) -> ColumnFacetOutput:
        _ = normalized_query
        _ = base_query
        return ColumnFacetOutput(
            facets=[
                ColumnFacet(column=column, facet_terms=[column.replace("_", " ")])
                for column in sparse_columns
            ]
        )


class DefaultColumnFacetGenerator(ColumnFacetGenerator):
    def __init__(
        self,
        *,
        model: str = DEFAULT_COLUMN_FACET_GENERATOR_MODEL,
        llm_client: StructuredLlmClient | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._model = model
        self._llm_client = llm_client
        self._openai_api_key = openai_api_key

    def generate(
        self,
        *,
        normalized_query: str,
        base_query: str,
        sparse_columns: list[str],
    ) -> ColumnFacetOutput:
        if not sparse_columns:
            return ColumnFacetOutput(facets=[])

        output = self._client().parse(
            model=self._model,
            system_prompt=COLUMN_FACET_GENERATOR_SYSTEM_PROMPT,
            user_content=_build_payload(
                normalized_query=normalized_query,
                base_query=base_query,
                sparse_columns=sparse_columns,
            ),
            response_model=ColumnFacetOutput,
            reasoning_effort=DEFAULT_COLUMN_FACET_REASONING_EFFORT,
        )
        facets_by_column: dict[str, ColumnFacet] = {
            facet.column: facet
            for facet in output.facets
            if facet.column in sparse_columns and facet.facet_terms
        }
        return ColumnFacetOutput(
            facets=[
                _normalized_facet(
                    facets_by_column.get(
                        column,
                        ColumnFacet(column=column, facet_terms=[column.replace("_", " ")]),
                    )
                )
                for column in sparse_columns
            ],
        )

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        api_key = self._openai_api_key or load_planner_runtime_config().openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")
        self._llm_client = OpenAiStructuredLlmClient(api_key=api_key)
        return self._llm_client


def _build_payload(
    *,
    normalized_query: str,
    base_query: str,
    sparse_columns: list[str],
) -> str:
    payload = {
        "normalized_query": normalized_query,
        "base_query": base_query,
        "sparse_columns": sparse_columns,
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _normalized_facet(facet: ColumnFacet) -> ColumnFacet:
    deduped_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in facet.facet_terms:
        normalized_term = " ".join(term.split()).strip()
        if not normalized_term:
            continue
        dedupe_key = normalized_term.casefold()
        if dedupe_key in seen_terms:
            continue
        deduped_terms.append(normalized_term)
        seen_terms.add(dedupe_key)
        if len(deduped_terms) >= 4:
            break
    if not deduped_terms:
        deduped_terms = [facet.column.replace("_", " ")]
    return ColumnFacet(column=facet.column, facet_terms=deduped_terms)
