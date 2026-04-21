from __future__ import annotations

import json
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import load_extractor_runtime_config
from backend.app.contracts import (
    EvidenceItem,
    ExtractedEntity,
    ExtractorOutput,
    FieldValue,
    PlannerOutput,
)
from backend.app.helpers.column_aware_chunk_ranker import ColumnAwareChunkRankingOutput
from backend.app.prompts import ENTITY_GAP_FILLER_SYSTEM_PROMPT


DEFAULT_GAP_FILLER_MODEL = "gpt-5-mini"
DEFAULT_GAP_FILLER_REASONING_EFFORT = "minimal"
MAX_GAP_FILLER_CONCURRENCY = 3
MAX_GAP_FILLER_CHUNKS_PER_ENTITY = 9


class GapFillColumnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_name: str
    value: str | int | float | bool | list[str] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class GapFillEntityOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_name: str
    fields: list[GapFillColumnDecision] = Field(default_factory=list)


@dataclass(frozen=True)
class EntityGapFillUpdate:
    entity_name: str
    fields: dict[str, FieldValue]


@dataclass(frozen=True)
class EntityGapFillResult:
    updates: list[EntityGapFillUpdate]
    fields_filled: int


class EntityGapFiller(ABC):
    @abstractmethod
    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
        ranking_output: ColumnAwareChunkRankingOutput,
    ) -> EntityGapFillResult:
        """Fill missing fields from new breadth-v2 chunks only."""


class PlaceholderEntityGapFiller(EntityGapFiller):
    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
        ranking_output: ColumnAwareChunkRankingOutput,
    ) -> EntityGapFillResult:
        _ = planner_output
        _ = extractor_output
        _ = ranking_output
        return EntityGapFillResult(updates=[], fields_filled=0)


class DefaultEntityGapFiller(EntityGapFiller):
    def __init__(
        self,
        *,
        model: str = DEFAULT_GAP_FILLER_MODEL,
        llm_client: StructuredLlmClient | None = None,
        openai_api_key: str | None = None,
    ) -> None:
        self._model = model
        self._llm_client = llm_client
        self._openai_api_key = openai_api_key

    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
        ranking_output: ColumnAwareChunkRankingOutput,
    ) -> EntityGapFillResult:
        work_items = [
            (entity, _missing_columns(entity), _evidence_chunks_by_column(entity.entity_name, ranking_output))
            for entity in extractor_output.entities
        ]
        work_items = [
            (entity, missing_columns, evidence_chunks_by_column)
            for entity, missing_columns, evidence_chunks_by_column in work_items
            if missing_columns and evidence_chunks_by_column
        ]
        if not work_items:
            return EntityGapFillResult(updates=[], fields_filled=0)

        max_workers = min(MAX_GAP_FILLER_CONCURRENCY, len(work_items))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            updates = list(
                executor.map(
                    lambda item: self._fill_entity(
                        planner_output=planner_output,
                        entity=item[0],
                        missing_columns=item[1],
                        evidence_chunks_by_column=item[2],
                    ),
                    work_items,
                )
            )

        realized_updates = [update for update in updates if update is not None]
        fields_filled = sum(len(update.fields) for update in realized_updates)
        return EntityGapFillResult(updates=realized_updates, fields_filled=fields_filled)

    def _fill_entity(
        self,
        *,
        planner_output: PlannerOutput,
        entity: ExtractedEntity,
        missing_columns: list[str],
        evidence_chunks_by_column: dict[str, list[_GapFillChunk]],
    ) -> EntityGapFillUpdate | None:
        model_output = self._client().parse(
            model=self._model,
            system_prompt=ENTITY_GAP_FILLER_SYSTEM_PROMPT,
            user_content=_build_gap_filler_payload(
                planner_output=planner_output,
                entity=entity,
                missing_columns=missing_columns,
                evidence_chunks_by_column=evidence_chunks_by_column,
            ),
            response_model=GapFillEntityOutput,
            reasoning_effort=DEFAULT_GAP_FILLER_REASONING_EFFORT,
        )
        if model_output.entity_name.strip() != entity.entity_name:
            return None

        field_updates: dict[str, FieldValue] = {}
        evidence_by_chunk_id = {
            gap_chunk.chunk_id: gap_chunk
            for chunks in evidence_chunks_by_column.values()
            for gap_chunk in chunks
        }
        for field in model_output.fields:
            if field.column_name not in missing_columns or field.value is None:
                continue
            evidence = [
                EvidenceItem(
                    source_url=gap_chunk.source_url,
                    source_title=gap_chunk.source_title,
                    supporting_snippet=gap_chunk.text,
                )
                for chunk_id in field.supporting_chunk_ids
                if (gap_chunk := evidence_by_chunk_id.get(chunk_id)) is not None
            ]
            if not evidence:
                continue
            field_updates[field.column_name] = FieldValue(
                value=field.value,
                confidence=field.confidence,
                evidence=evidence,
            )

        if not field_updates:
            return None
        return EntityGapFillUpdate(entity_name=entity.entity_name, fields=field_updates)

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        api_key = self._openai_api_key or load_extractor_runtime_config().openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")
        self._llm_client = OpenAiStructuredLlmClient(api_key=api_key)
        return self._llm_client


class GapFillMerger:
    def merge(
        self,
        *,
        extractor_output: ExtractorOutput,
        gap_fill_result: EntityGapFillResult,
    ) -> ExtractorOutput:
        updates_by_entity = {update.entity_name: update for update in gap_fill_result.updates}
        merged_entities: list[ExtractedEntity] = []
        for entity in extractor_output.entities:
            update = updates_by_entity.get(entity.entity_name)
            if update is None:
                merged_entities.append(entity)
                continue
            merged_fields = dict(entity.fields)
            for column, field_value in update.fields.items():
                existing = merged_fields.get(column)
                if existing is not None and existing.value is not None:
                    continue
                merged_fields[column] = field_value
            merged_entities.append(entity.model_copy(update={"fields": merged_fields}))
        return ExtractorOutput(entities=merged_entities)


@dataclass(frozen=True)
class _GapFillChunk:
    chunk_id: str
    source_url: str
    source_title: str
    text: str


def _missing_columns(entity: ExtractedEntity) -> list[str]:
    return [
        column
        for column, field_value in entity.fields.items()
        if field_value.value is None
    ]


def _evidence_chunks_by_column(
    entity_name: str,
    ranking_output: ColumnAwareChunkRankingOutput,
) -> dict[str, list[_GapFillChunk]]:
    source_url_and_title_by_id = {
        source.source_id: (str(source.url), source.title)
        for source in ranking_output.url_sources
    }
    chunk_text_by_id = {
        chunk.chunk_id: chunk.text
        for source in ranking_output.url_sources
        for chunk in source.chunks
    }
    chunks_by_column: dict[str, list[_GapFillChunk]] = {}
    for ranked_chunk in ranking_output.ranked_chunks:
        if ranked_chunk.entity_name != entity_name:
            continue
        source_url, source_title = source_url_and_title_by_id.get(ranked_chunk.source_id, ("", ""))
        chunk_text = chunk_text_by_id.get(ranked_chunk.chunk_id)
        if not source_url or not chunk_text:
            continue
        chunks_by_column.setdefault(ranked_chunk.column, []).append(
            _GapFillChunk(
                chunk_id=ranked_chunk.chunk_id,
                source_url=source_url,
                source_title=source_title,
                text=chunk_text,
            )
        )
    return chunks_by_column


def _build_gap_filler_payload(
    *,
    planner_output: PlannerOutput,
    entity: ExtractedEntity,
    missing_columns: list[str],
    evidence_chunks_by_column: dict[str, list[_GapFillChunk]],
) -> str:
    existing_fields = {
        column: field_value.value
        for column, field_value in entity.fields.items()
        if field_value.value is not None
    }
    chunk_payloads = []
    for column in missing_columns:
        for chunk in evidence_chunks_by_column.get(column, [])[:MAX_GAP_FILLER_CHUNKS_PER_ENTITY]:
            chunk_payloads.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "column": column,
                    "source_url": chunk.source_url,
                    "source_title": chunk.source_title,
                    "text": chunk.text,
                }
            )

    payload = {
        "normalized_query": planner_output.normalized_query,
        "entity_type": planner_output.entity_type,
        "entity_name": entity.entity_name,
        "existing_fields": existing_fields,
        "missing_columns": missing_columns,
        "evidence_chunks": chunk_payloads,
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)
