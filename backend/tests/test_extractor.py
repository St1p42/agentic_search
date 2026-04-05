from __future__ import annotations

import json

from pydantic import HttpUrl

from backend.app.contracts import (
    EvidenceStore,
    ExtractorLightOutput,
    PlannerOutput,
)
from backend.app.stages.extractor import (
    ExtractorColumnDecision,
    ExtractorEntityModelOutput,
    LlmExtractorStage,
)


class FakeStructuredLlmClient:
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


def test_llm_extractor_stage_anchors_entity_and_maps_chunk_evidence() -> None:
    llm_client = FakeStructuredLlmClient()
    stage = LlmExtractorStage(model="gpt-5-mini", llm_client=llm_client)

    output = stage.run(
        planner_output=PlannerOutput(
            entity_type="startup",
            query_mode="topic_entity_discovery",
            schema_columns=["name", "website", "location", "focus_area"],
            core_aspects=["focus_area", "location"],
            base_query="AI startups in healthcare",
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query="AI startups in healthcare",
        ),
        extractor_light_output=ExtractorLightOutput(
            candidate_names=["Acme Health"],
            name_to_source_urls={"Acme Health": [HttpUrl("https://acmehealth.com/about")]},
            mention_counts={"Acme Health": 1},
        ),
        evidence_store=EvidenceStore(
            chunks_by_entity={
                "Acme Health": [
                    {
                        "text": "Acme Health develops clinical AI systems for hospitals and care teams.",
                        "source_url": "https://acmehealth.com/about",
                        "source_title": "About Acme Health",
                        "source_role": "verification",
                        "source_quality": "high",
                        "officiality": "official",
                        "origin": "brave_llm",
                        "aspect_coverage": ["focus_area"],
                    }
                ]
            },
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
    stage = LlmExtractorStage(model="gpt-5-mini", llm_client=llm_client)

    candidate_names = [f"Entity {index:02d}" for index in range(1, 18)]
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
        planner_output=PlannerOutput(
            entity_type="startup",
            query_mode="topic_entity_discovery",
            schema_columns=["name", "focus_area"],
            core_aspects=["focus_area"],
            base_query="AI startups in healthcare",
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query="AI startups in healthcare",
        ),
        extractor_light_output=ExtractorLightOutput(
            candidate_names=candidate_names,
            name_to_source_urls={},
            mention_counts={entity_name: 1 for entity_name in candidate_names},
        ),
        evidence_store=EvidenceStore(
            chunks_by_entity=chunks_by_entity,
            entity_scores=entity_scores,
        ),
    )

    assert len(output.entities) == 10
    assert output.entities[0].entity_name == "Entity 01"
    assert output.entities[-1].entity_name == "Entity 10"
    assert [json.loads(call["user_content"])["entity_anchor"] for call in llm_client.calls] == [
        f"Entity {index:02d}" for index in range(1, 11)
    ]
