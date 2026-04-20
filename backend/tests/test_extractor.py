from __future__ import annotations

import json
import threading
import time

from pydantic import HttpUrl

from backend.app.api_clients import StructuredLlmClient
from backend.app.helpers.entity_reranker import EntityRankingResult, EntityReranker, RankedEntity, EntityRankingFeatures
from backend.app.stages.extractor import (
    ExtractorColumnDecision,
    ExtractorEntityModelOutput,
    LlmExtractorStage,
)
from backend.tests.fixtures.factories import (
    make_evidence_chunk,
    make_evidence_store,
    make_extractor_light_output,
    make_planner_output,
)


class FakeStructuredLlmClient(StructuredLlmClient):
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[ExtractorEntityModelOutput],
        reasoning_effort: str | None = None,
    ) -> ExtractorEntityModelOutput:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "reasoning_effort": reasoning_effort or "",
            }
        )
        _ = response_model
        return ExtractorEntityModelOutput(
            entity_name="Acme Health",
            provisional=False,
            fields=[
                ExtractorColumnDecision(
                    column_name="focus_area",
                    value="clinical AI systems",
                    confidence=0.82,
                    supporting_chunk_ids=["c1"],
                )
            ],
        )


class ConcurrentFakeStructuredLlmClient(StructuredLlmClient):
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[ExtractorEntityModelOutput],
        reasoning_effort: str | None = None,
    ) -> ExtractorEntityModelOutput:
        _ = model
        _ = system_prompt
        _ = response_model
        _ = reasoning_effort
        payload = json.loads(user_content)
        entity_name = payload["entity_anchor"]

        with self._lock:
            self.calls.append(entity_name)
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)

        try:
            time.sleep(0.05)
            return ExtractorEntityModelOutput(
                entity_name=entity_name,
                provisional=False,
                fields=[
                    ExtractorColumnDecision(
                        column_name="focus_area",
                        value=f"{entity_name} focus",
                        confidence=0.9,
                        supporting_chunk_ids=["c1"],
                    )
                ],
            )
        finally:
            with self._lock:
                self._in_flight -= 1


class StubEntityReranker(EntityReranker):
    def __init__(self, ranked_entity_names: list[str]) -> None:
        self._ranked_entity_names = ranked_entity_names

    def run(self, *, planner_output, extractor_light_output, evidence_store) -> EntityRankingResult:
        _ = planner_output
        _ = extractor_light_output
        _ = evidence_store
        return EntityRankingResult(
            kept_entities=[
                RankedEntity(
                    entity_name=entity_name,
                    candidate_type="core",
                    support_score=1.0,
                    query_alignment_score=1.0,
                    final_score=1.0,
                    features=EntityRankingFeatures(
                        unique_source_count=1,
                        deduped_unique_chunk_count=1,
                        query_variant_coverage_count=1,
                        best_source_quality_score=1.0,
                        avg_selected_chunk_rank_score=1.0,
                        source_concentration_ratio=1.0,
                    ),
                )
                for entity_name in self._ranked_entity_names
            ],
            filtered_entities=[],
        )


def test_llm_extractor_stage_anchors_entity_and_maps_chunk_evidence() -> None:
    llm_client = FakeStructuredLlmClient()
    stage = LlmExtractorStage(model="gpt-5-mini", llm_client=llm_client)

    output = stage.run(
        planner_output=make_planner_output(),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Health"],
            name_to_source_urls={"Acme Health": [HttpUrl("https://acmehealth.com/about")]},
            mention_counts={"Acme Health": 1},
        ),
        evidence_store=make_evidence_store(
            chunks_by_entity={"Acme Health": [make_evidence_chunk()]},
            entity_scores={"Acme Health": 1.0},
        ),
    )

    assert output.entities[0].entity_name == "Acme Health"
    assert output.entities[0].fields["name"].value == "Acme Health"
    assert output.entities[0].fields["focus_area"].value == "clinical AI systems"
    assert str(output.entities[0].fields["focus_area"].evidence[0].source_url) == "https://acmehealth.com/about"

    payload = json.loads(llm_client.calls[0]["user_content"])
    assert payload["entity_anchor"] == "Acme Health"
    assert payload["schema_columns"] == ["name", "website", "location", "focus_area"]
    assert payload["evidence_chunks"][0]["chunk_id"] == "c1"


def test_llm_extractor_stage_keeps_only_top_ranked_ten_entities() -> None:
    llm_client = FakeStructuredLlmClient()
    candidate_names = [f"Entity {index:02d}" for index in range(1, 18)]
    stage = LlmExtractorStage(
        model="gpt-5-mini",
        llm_client=llm_client,
        entity_reranker=StubEntityReranker(candidate_names),
    )

    chunks_by_entity = {
        entity_name: [
            {
                "text": f"{entity_name} has usable evidence for extraction and ranking.",
                "source_url": f"https://example.com/{index:02d}",
                "source_title": entity_name,
                "source_role": "corroboration",
                "source_quality": "high",
                "officiality": "third_party",
                "origin": "brave_llm",
                "aspect_coverage": ["focus_area"],
            }
        ]
        for index, entity_name in enumerate(candidate_names, start=1)
    }
    entity_scores = {
        entity_name: float(18 - index)
        for index, entity_name in enumerate(candidate_names, start=1)
    }

    output = stage.run(
        planner_output=make_planner_output(
            schema_columns=["name", "focus_area"],
            core_aspects=["focus_area"],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=candidate_names,
            name_to_source_urls={},
            mention_counts={entity_name: 1 for entity_name in candidate_names},
        ),
        evidence_store=make_evidence_store(chunks_by_entity=chunks_by_entity, entity_scores=entity_scores),
    )

    assert len(output.entities) == 10
    assert output.entities[0].entity_name == "Entity 01"
    assert output.entities[-1].entity_name == "Entity 10"
    assert [json.loads(call["user_content"])["entity_anchor"] for call in llm_client.calls] == [
        f"Entity {index:02d}" for index in range(1, 11)
    ]


def test_llm_extractor_stage_runs_multiple_entity_requests_concurrently_and_preserves_order() -> None:
    llm_client = ConcurrentFakeStructuredLlmClient()
    candidate_names = [f"Entity {index:02d}" for index in range(1, 6)]
    stage = LlmExtractorStage(
        model="gpt-5-mini",
        llm_client=llm_client,
        entity_reranker=StubEntityReranker(candidate_names),
    )
    chunks_by_entity = {
        entity_name: [
            {
                "text": f"{entity_name} has usable evidence for extraction.",
                "source_url": f"https://example.com/{index:02d}",
                "source_title": entity_name,
                "source_role": "corroboration",
                "source_quality": "high",
                "officiality": "third_party",
                "origin": "brave_llm",
                "aspect_coverage": ["focus_area"],
            }
        ]
        for index, entity_name in enumerate(candidate_names, start=1)
    }

    output = stage.run(
        planner_output=make_planner_output(
            schema_columns=["name", "focus_area"],
            core_aspects=["focus_area"],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=candidate_names,
            name_to_source_urls={},
            mention_counts={entity_name: 1 for entity_name in candidate_names},
        ),
        evidence_store=make_evidence_store(
            chunks_by_entity=chunks_by_entity,
            entity_scores={entity_name: float(6 - index) for index, entity_name in enumerate(candidate_names, start=1)},
        ),
    )

    assert [entity.entity_name for entity in output.entities] == candidate_names
    assert [entity.fields["focus_area"].value for entity in output.entities] == [
        f"{entity_name} focus" for entity_name in candidate_names
    ]
    assert llm_client.max_in_flight > 1
    assert llm_client.max_in_flight <= 3
