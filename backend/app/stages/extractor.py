from __future__ import annotations

"""Extractor stage interface plus placeholder and LLM-backed implementations."""

from concurrent.futures import ThreadPoolExecutor
import json
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import (
    DEFAULT_EXTRACTOR_MODEL,
    ExtractorRuntimeConfig,
    load_extractor_runtime_config,
)
from backend.app.contracts import (
    EvidenceChunk,
    EvidenceItem,
    EvidenceStore,
    ExtractedEntity,
    ExtractorLightOutput,
    ExtractorOutput,
    FieldValue,
    PlannerOutput,
)
from backend.app.helpers import DefaultEntityReranker, EntityReranker
from backend.app.helpers.entity_reranker import EntityRankingResult
from backend.app.prompts import EXTRACTOR_SYSTEM_PROMPT


MAX_EVIDENCE_CHUNKS_PER_ENTITY = 12
MAX_EXTRACTOR_ENTITIES = 10
MAX_EXTRACTOR_CONCURRENCY = 3


class ExtractorStage(Protocol):
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
        entity_ranking_result: EntityRankingResult | None = None,
    ) -> ExtractorOutput:
        """Extract structured candidate entities from entity-centric evidence chunks."""


class PlaceholderExtractorStage:
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
        entity_ranking_result: EntityRankingResult | None = None,
    ) -> ExtractorOutput:
        _ = planner_output
        _ = extractor_light_output
        _ = evidence_store
        return prior_output or ExtractorOutput(entities=[])


class ExtractorFieldDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | int | float | bool | list[str] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class ExtractorColumnDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column_name: str
    value: str | int | float | bool | list[str] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_chunk_ids: list[str] = Field(default_factory=list)


class ExtractorEntityModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_name: str
    provisional: bool = False
    fields: list[ExtractorColumnDecision] = Field(default_factory=list)


class LlmExtractorStage:
    def __init__(
        self,
        model: str = DEFAULT_EXTRACTOR_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: ExtractorRuntimeConfig | None = None,
        entity_reranker: EntityReranker | None = None,
    ) -> None:
        self.model = model
        self.reasoning_effort = "minimal"
        self._llm_client = llm_client
        self._runtime_config = runtime_config
        self._entity_reranker = entity_reranker or DefaultEntityReranker()

    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
        entity_ranking_result: EntityRankingResult | None = None,
    ) -> ExtractorOutput:
        prior_by_name = {
            entity.entity_name: entity
            for entity in (prior_output.entities if prior_output else [])
        }
        ranking_result = entity_ranking_result or self._entity_reranker.run(
            planner_output=planner_output,
            extractor_light_output=extractor_light_output,
            evidence_store=evidence_store,
        )
        ranked_entity_names = ranking_result.ranked_entity_names[:MAX_EXTRACTOR_ENTITIES]
        entities_by_name: dict[str, ExtractedEntity] = {}
        pending_names: list[str] = []

        for entity_name in ranked_entity_names:
            chunks = evidence_store.chunks_by_entity.get(entity_name, [])
            if not chunks:
                entities_by_name[entity_name] = prior_by_name.get(entity_name) or _empty_extracted_entity(
                    entity_name=entity_name,
                    schema_columns=planner_output.schema_columns,
                )
                continue
            pending_names.append(entity_name)

        if pending_names:
            max_workers = min(MAX_EXTRACTOR_CONCURRENCY, len(pending_names))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                extracted_entities = executor.map(
                    lambda pending_entity_name: self._extract_entity(
                        planner_output=planner_output,
                        entity_name=pending_entity_name,
                        evidence_chunks=evidence_store.chunks_by_entity.get(pending_entity_name, []),
                    ),
                    pending_names,
                )
                for extracted_entity in extracted_entities:
                    entities_by_name[extracted_entity.entity_name] = extracted_entity

        return ExtractorOutput(
            entities=[
                entities_by_name[entity_name]
                for entity_name in ranked_entity_names
                if entity_name in entities_by_name
            ]
        )

    def _extract_entity(
        self,
        *,
        planner_output: PlannerOutput,
        entity_name: str,
        evidence_chunks: list[EvidenceChunk],
    ) -> ExtractedEntity:
        model_output = self._client().parse(
            model=self.model,
            system_prompt=EXTRACTOR_SYSTEM_PROMPT,
            user_content=_build_extractor_payload(
                planner_output=planner_output,
                entity_name=entity_name,
                evidence_chunks=evidence_chunks,
            ),
            response_model=ExtractorEntityModelOutput,
            reasoning_effort=self.reasoning_effort,
        )
        return _to_extracted_entity(
            anchor_entity_name=entity_name,
            planner_output=planner_output,
            evidence_chunks=evidence_chunks,
            model_output=model_output,
        )

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        extractor_config = self._runtime_config or load_extractor_runtime_config()
        if not extractor_config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")

        self.model = self.model or extractor_config.model
        self._llm_client = OpenAiStructuredLlmClient(api_key=extractor_config.openai_api_key)
        return self._llm_client


def build_extractor_stage(
    runtime_config: ExtractorRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
    entity_reranker: EntityReranker | None = None,
) -> ExtractorStage:
    config = runtime_config or load_extractor_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderExtractorStage()
    if config.mode == "llm":
        return LlmExtractorStage(
            model=config.model,
            llm_client=llm_client,
            runtime_config=config,
            entity_reranker=entity_reranker,
        )
    raise ValueError(f"Unsupported extractor mode: {config.mode}")


def _build_extractor_payload(
    *,
    planner_output: PlannerOutput,
    entity_name: str,
    evidence_chunks: list[EvidenceChunk],
) -> str:
    payload = {
        "normalized_query": planner_output.normalized_query,
        "entity_type": planner_output.entity_type,
        "schema_columns": planner_output.schema_columns,
        "core_aspects": planner_output.core_aspects,
        "entity_anchor": entity_name,
        "evidence_chunks": [
            {
                "chunk_id": f"c{index}",
                "source_url": str(chunk.source_url),
                "source_title": chunk.source_title,
                "source_role": chunk.source_role.value,
                "source_quality": chunk.source_quality.value,
                "officiality": chunk.officiality.value,
                "aspect_coverage": chunk.aspect_coverage,
                "text": chunk.text,
            }
            for index, chunk in enumerate(evidence_chunks[:MAX_EVIDENCE_CHUNKS_PER_ENTITY], start=1)
        ],
    }
    return json.dumps(payload, ensure_ascii=True, indent=2)


def _to_extracted_entity(
    *,
    anchor_entity_name: str,
    planner_output: PlannerOutput,
    evidence_chunks: list[EvidenceChunk],
    model_output: ExtractorEntityModelOutput,
) -> ExtractedEntity:
    chunk_id_to_chunk = {
        f"c{index}": chunk
        for index, chunk in enumerate(evidence_chunks[:MAX_EVIDENCE_CHUNKS_PER_ENTITY], start=1)
    }

    if model_output.entity_name.strip() != anchor_entity_name:
        return _empty_extracted_entity(
            entity_name=anchor_entity_name,
            schema_columns=planner_output.schema_columns,
        )

    model_fields_by_column = {
        field.column_name: ExtractorFieldDecision(
            value=field.value,
            confidence=field.confidence,
            supporting_chunk_ids=field.supporting_chunk_ids,
        )
        for field in model_output.fields
        if field.column_name in planner_output.schema_columns
    }

    fields = {
        column: _field_value_from_decision(
            decision=model_fields_by_column.get(column),
            chunk_id_to_chunk=chunk_id_to_chunk,
        )
        for column in planner_output.schema_columns
    }

    if "name" in fields and fields["name"].value is None and chunk_id_to_chunk:
        first_chunk = next(iter(chunk_id_to_chunk.values()))
        fields["name"] = FieldValue(
            value=anchor_entity_name,
            confidence=1.0,
            evidence=[_evidence_item(first_chunk)],
        )

    source_urls = _source_urls_for_fields(fields)
    return ExtractedEntity(
        candidate_id=anchor_entity_name,
        entity_name=anchor_entity_name,
        fields=fields,
        source_urls=source_urls,
        provisional=model_output.provisional,
    )


def _field_value_from_decision(
    *,
    decision: ExtractorFieldDecision | None,
    chunk_id_to_chunk: dict[str, EvidenceChunk],
) -> FieldValue:
    if decision is None or decision.value is None:
        return FieldValue(value=None, confidence=0.0, evidence=[])

    evidence = [
        _evidence_item(chunk_id_to_chunk[chunk_id])
        for chunk_id in decision.supporting_chunk_ids
        if chunk_id in chunk_id_to_chunk
    ]
    if not evidence:
        return FieldValue(value=None, confidence=0.0, evidence=[])

    return FieldValue(
        value=decision.value,
        confidence=decision.confidence,
        evidence=evidence,
    )


def _evidence_item(chunk: EvidenceChunk) -> EvidenceItem:
    return EvidenceItem(
        source_url=chunk.source_url,
        source_title=chunk.source_title,
        supporting_snippet=chunk.text,
        source_role=chunk.source_role,
        source_quality=chunk.source_quality,
        officiality=chunk.officiality,
    )


def _source_urls_for_fields(fields: dict[str, FieldValue]) -> list[str]:
    source_urls: list[str] = []
    seen_urls: set[str] = set()
    for field_value in fields.values():
        for evidence_item in field_value.evidence:
            url = str(evidence_item.source_url)
            if url in seen_urls:
                continue
            seen_urls.add(url)
            source_urls.append(url)
    return source_urls


def _empty_extracted_entity(
    *,
    entity_name: str,
    schema_columns: list[str],
) -> ExtractedEntity:
    return ExtractedEntity(
        candidate_id=entity_name,
        entity_name=entity_name,
        fields={column: FieldValue(value=None, confidence=0.0, evidence=[]) for column in schema_columns},
        source_urls=[],
        provisional=True,
    )
