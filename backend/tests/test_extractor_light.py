from __future__ import annotations

from typing import cast

from pydantic import HttpUrl

from backend.app.api_clients.llm_client import StructuredLlmClient, StructuredOutputT
from backend.app.stages.extractor_light import (
    ExtractorLightModelOutput,
    LlmExtractorLightStage,
)
from backend.tests.fixtures.factories import (
    make_chunk_ranking_output,
    make_planner_output,
    make_retrieved_chunk,
    make_url_source,
)


class FakeExtractorLightClient:
    def __init__(self, output: ExtractorLightModelOutput) -> None:
        self.output_payload = output.model_dump()
        self.calls: list[dict[str, str]] = []

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[StructuredOutputT],
        reasoning_effort: str | None = None,
    ) -> StructuredOutputT:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "response_model": response_model.__name__,
                "reasoning_effort": reasoning_effort or "",
            }
        )
        return response_model.model_validate(self.output_payload)


def _chunk_ranking_output():
    acme_url = HttpUrl("https://acmehealth.com/about")
    roundup_url = HttpUrl("https://roundup.example.com/health-ai")
    return make_chunk_ranking_output(
        url_sources=[
            make_url_source(
                source_id="jina:https://acmehealth.com/about",
                url=str(acme_url),
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://acmehealth.com/about#0",
                        source_id="jina:https://acmehealth.com/about",
                        text="Acme Health builds clinical AI systems. Acme Health serves hospitals.",
                    )
                ],
            ),
            make_url_source(
                source_id="jina:https://roundup.example.com/health-ai",
                url=str(roundup_url),
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://roundup.example.com/health-ai#0",
                        source_id="jina:https://roundup.example.com/health-ai",
                        text=(
                            "A roundup featuring Beta AI and Acme Health in healthcare AI. "
                            "Beta AI's platform supports triage."
                        ),
                    )
                ],
            ),
        ],
        selected_chunk_ids=[
            "jina:https://acmehealth.com/about#0",
            "jina:https://roundup.example.com/health-ai#0",
        ],
    )


def _as_structured_client(fake_client: FakeExtractorLightClient) -> StructuredLlmClient:
    return cast(StructuredLlmClient, cast(object, fake_client))


def test_llm_extractor_light_stage_builds_name_url_map_and_mentions() -> None:
    chunk_ranking_output = _chunk_ranking_output()
    acme_url = HttpUrl("https://acmehealth.com/about")
    roundup_url = HttpUrl("https://roundup.example.com/health-ai")
    fake_client = FakeExtractorLightClient(
        ExtractorLightModelOutput(
            candidate_names=[" Acme Health ", "Beta AI", "Acme Health"],
        )
    )
    extractor_light = LlmExtractorLightStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = extractor_light.run(
        planner_output=make_planner_output(),
        chunk_ranking_output=chunk_ranking_output,
    )

    assert output.candidate_names == ["Acme Health", "Beta AI"]
    assert output.name_to_source_urls["Acme Health"] == [acme_url, roundup_url]
    assert output.name_to_source_urls["Beta AI"] == [roundup_url]
    assert output.mention_counts == {
        "Acme Health": 3,
        "Beta AI": 2,
    }
    assert len(fake_client.calls) == 1
    assert "entity_type: startup" in fake_client.calls[0]["user_content"]
    assert "[c1] Acme Health builds clinical AI systems." in fake_client.calls[0]["user_content"]
    assert "https://acmehealth.com/about" not in fake_client.calls[0]["user_content"]
    assert fake_client.calls[0]["reasoning_effort"] == "minimal"


def test_llm_extractor_light_stage_returns_empty_output_without_passages() -> None:
    fake_client = FakeExtractorLightClient(
        ExtractorLightModelOutput(
            candidate_names=["Should Not Be Used"],
        )
    )
    extractor_light = LlmExtractorLightStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = extractor_light.run(
        planner_output=make_planner_output(),
        chunk_ranking_output=make_chunk_ranking_output(url_sources=[], ranked_chunks=[], selected_chunk_ids=[]),
    )

    assert output.candidate_names == []
    assert output.name_to_source_urls == {}
    assert output.mention_counts == {}
    assert fake_client.calls == []


def test_llm_extractor_light_stage_drops_shorter_overlapping_name_variants() -> None:
    acme_url = HttpUrl("https://example.com/apple")
    chunk_ranking_output = make_chunk_ranking_output(
        url_sources=[
            make_url_source(
                source_id="jina:https://example.com/apple",
                url=str(acme_url),
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/apple#0",
                        source_id="jina:https://example.com/apple",
                        text=(
                            "Apple iPhone 17 Pro Max is the top pick. "
                            "The iPhone 17 Pro Max camera system is excellent."
                        ),
                    )
                ],
            )
        ],
        selected_chunk_ids=["jina:https://example.com/apple#0"],
    )
    fake_client = FakeExtractorLightClient(
        ExtractorLightModelOutput(
            candidate_names=["Apple iPhone 17 Pro Max", "iPhone 17 Pro Max"],
        )
    )
    extractor_light = LlmExtractorLightStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = extractor_light.run(
        planner_output=make_planner_output(),
        chunk_ranking_output=chunk_ranking_output,
    )

    assert output.candidate_names == ["Apple iPhone 17 Pro Max"]
    assert output.name_to_source_urls == {"Apple iPhone 17 Pro Max": [acme_url]}
    assert output.mention_counts == {"Apple iPhone 17 Pro Max": 1}


def test_llm_extractor_light_stage_filters_generic_and_boilerplate_candidates() -> None:
    source_url = HttpUrl("https://example.com/healthcare-ai")
    chunk_ranking_output = make_chunk_ranking_output(
        url_sources=[
            make_url_source(
                source_id="jina:https://example.com/healthcare-ai",
                url=str(source_url),
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/healthcare-ai#0",
                        source_id="jina:https://example.com/healthcare-ai",
                        text=(
                            "Acme Health is featured alongside AI startups in healthcare. "
                            "About Us and Team describe the company. "
                            "Apple/Samsung is a comparison, while Platform is generic."
                        ),
                    )
                ],
            )
        ],
        selected_chunk_ids=["jina:https://example.com/healthcare-ai#0"],
    )
    fake_client = FakeExtractorLightClient(
        ExtractorLightModelOutput(
            candidate_names=["Acme Health", "AI startups", "About Us", "Apple/Samsung", "Platform"],
        )
    )
    extractor_light = LlmExtractorLightStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = extractor_light.run(
        planner_output=make_planner_output(),
        chunk_ranking_output=chunk_ranking_output,
    )

    assert output.candidate_names == ["Acme Health"]
    assert output.name_to_source_urls == {"Acme Health": [source_url]}
    assert output.mention_counts == {"Acme Health": 1}
