from __future__ import annotations

import json
from typing import cast

from pydantic import HttpUrl

from backend.app.api_clients.llm_client import StructuredLlmClient, StructuredOutputT
from backend.app.contracts import AssessorPass, OfficialityLevel, SourceQuality, SourceRole
from backend.app.helpers.evidence_store_builder import DefaultEvidenceStoreBuilder
from backend.app.stages.assessor import (
    AssessorModelOutput,
    AssessorSourceDecision,
    LlmSourceAssessorStage,
)
from backend.tests.fixtures.factories import (
    make_assessed_source,
    make_assessor_output,
    make_brave_context_output,
    make_brave_context_passage,
    make_extractor_light_output,
    make_planner_output,
    make_search_result,
    make_searcher_output,
)


class FakeAssessorClient:
    def __init__(self, output: AssessorModelOutput) -> None:
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
        _ = reasoning_effort
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "response_model": response_model.__name__,
            }
        )
        return response_model.model_validate(self.output_payload)


class BatchAwareFakeAssessorClient:
    def __init__(self) -> None:
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
        _ = reasoning_effort
        payload = json.loads(user_content)
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "response_model": response_model.__name__,
            }
        )
        return response_model.model_validate(
            {
                "assessed_sources": [
                    {
                        "source_url": source["source_url"],
                        "source_role": "corroboration",
                        "source_quality": "high",
                        "officiality": "third_party",
                        "estimated_aspect_coverage": ["focus_area"],
                        "evidence_sufficiency": 0.7,
                    }
                    for source in payload["sources"]
                ]
            }
        )


def _as_structured_client(fake_client: object) -> StructuredLlmClient:
    return cast(StructuredLlmClient, cast(object, fake_client))


def test_llm_assessor_stage_returns_source_triage_only() -> None:
    official_result = make_search_result(
        url="https://acmehealth.com/about",
        title="About Acme Health",
        snippet="Acme Health builds clinical AI systems.",
        domain="acmehealth.com",
        rank=1,
    )
    roundup_result = make_search_result(
        url="https://roundup.example.com/beta-ai",
        title="Top Healthcare AI Startups",
        snippet="Beta AI appears in a third-party startup roundup.",
        domain="roundup.example.com",
        rank=2,
    )
    searcher_output = make_searcher_output(
        raw_results=[official_result, roundup_result],
        shortlisted_results=[official_result, roundup_result],
    )
    brave_context_output = make_brave_context_output(
        passages_by_url={
            official_result.url: [
                make_brave_context_passage(
                    source_url=str(official_result.url),
                    passage_text="Acme Health develops clinical AI in Boston.",
                    metadata={"title": "About Acme Health"},
                )
            ],
            roundup_result.url: [
                make_brave_context_passage(
                    source_url=str(roundup_result.url),
                    passage_text="Beta AI is mentioned in a list of healthcare startups.",
                    metadata={"title": "Top Healthcare AI Startups"},
                )
            ],
        }
    )
    assessor = LlmSourceAssessorStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(
            FakeAssessorClient(
                AssessorModelOutput(
                        assessed_sources=[
                            AssessorSourceDecision(
                                source_url=str(official_result.url),
                                source_role=SourceRole.VERIFICATION,
                                source_quality=SourceQuality.HIGH,
                                officiality=OfficialityLevel.OFFICIAL,
                                estimated_aspect_coverage=["focus_area", "location"],
                                evidence_sufficiency=0.9,
                            ),
                            AssessorSourceDecision(
                                source_url=str(roundup_result.url),
                                source_role=SourceRole.DISCOVERY,
                                source_quality=SourceQuality.MEDIUM,
                                officiality=OfficialityLevel.THIRD_PARTY,
                            estimated_aspect_coverage=["focus_area"],
                            evidence_sufficiency=0.4,
                        ),
                    ]
                )
            )
        ),
    )

    first_pass_output = assessor.run(
        planner_output=make_planner_output(),
        searcher_output=searcher_output,
        brave_context_output=brave_context_output,
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Health", "Beta AI"],
            name_to_source_urls={
                "Acme Health": [HttpUrl("https://acmehealth.com/about")],
                "Beta AI": [HttpUrl("https://roundup.example.com/beta-ai")],
            },
            mention_counts={"Acme Health": 4, "Beta AI": 2},
        ),
        pass_type=AssessorPass.FIRST_PASS,
    )

    assert first_pass_output.verification_gaps == []
    assert first_pass_output.selected_jina_urls == []
    assert first_pass_output.assessed_sources[0].source_role == SourceRole.VERIFICATION
    assert first_pass_output.assessed_sources[1].estimated_aspect_coverage == ["focus_area"]
    assert all(source.should_deep_fetch is False for source in first_pass_output.assessed_sources)


def test_llm_assessor_stage_filters_low_quality_sources_before_llm() -> None:
    low_quality_result = make_search_result(
        url="https://reddit.com/r/startups/comments/acme",
        title="Acme thread",
        snippet="",
        domain="reddit.com",
        rank=4,
    )
    official_result = make_search_result(
        url="https://acmehealth.com/about",
        title="About Acme Health",
        snippet="Acme Health builds clinical AI systems.",
        domain="acmehealth.com",
        rank=1,
    )
    searcher_output = make_searcher_output(
        raw_results=[official_result, low_quality_result],
        shortlisted_results=[official_result, low_quality_result],
    )
    brave_context_output = make_brave_context_output(
        passages_by_url={
            official_result.url: [
                make_brave_context_passage(
                    source_url=str(official_result.url),
                    passage_text="Acme Health develops clinical AI in Boston.",
                    metadata={"title": "About Acme Health"},
                )
            ],
            low_quality_result.url: [
                make_brave_context_passage(
                    source_url=str(low_quality_result.url),
                    passage_text="fallback snippet",
                    metadata={"title": "Acme thread", "fallback": True},
                )
            ],
        }
    )
    fake_client = FakeAssessorClient(
        AssessorModelOutput(
            assessed_sources=[
                AssessorSourceDecision(
                    source_url=str(official_result.url),
                    source_role=SourceRole.VERIFICATION,
                    source_quality=SourceQuality.HIGH,
                    officiality=OfficialityLevel.OFFICIAL,
                    estimated_aspect_coverage=["focus_area"],
                    evidence_sufficiency=0.9,
                )
            ]
        )
    )
    assessor = LlmSourceAssessorStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = assessor.run(
        planner_output=make_planner_output(),
        searcher_output=searcher_output,
        brave_context_output=brave_context_output,
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Health"],
            name_to_source_urls={"Acme Health": [HttpUrl("https://acmehealth.com/about")]},
            mention_counts={"Acme Health": 2},
        ),
    )

    assert len(fake_client.calls) == 1
    payload = fake_client.calls[0]["user_content"]
    assert str(low_quality_result.url) not in payload
    dropped = next(source for source in output.assessed_sources if str(source.result.url) == str(low_quality_result.url))
    assert dropped.filtered_out is True
    assert dropped.fetch_reason == "low_quality"


def test_evidence_builder_skips_filtered_sources() -> None:
    result = make_search_result(
        url="https://reddit.com/r/startups/comments/acme",
        title="Acme thread",
        snippet="",
        domain="reddit.com",
        rank=4,
    )
    passage = make_brave_context_passage(
        source_url=str(result.url),
        passage_text="This should never become evidence.",
        metadata={"title": "Acme thread", "fallback": True},
    )
    builder = DefaultEvidenceStoreBuilder()

    output = builder.run(
        brave_context_output=make_brave_context_output(passages_by_url={result.url: [passage]}),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Health"],
            name_to_source_urls={"Acme Health": [result.url]},
            mention_counts={"Acme Health": 1},
        ),
        assessor_output=make_assessor_output(
            assessed_sources=[
                make_assessed_source(
                    result=result,
                    brave_context_passages=[passage],
                    source_role=SourceRole.DISCOVERY,
                    source_quality=SourceQuality.LOW,
                    officiality=OfficialityLevel.THIRD_PARTY,
                    evidence_sufficiency=0.0,
                    filtered_out=True,
                )
            ]
        ),
    )

    assert output.chunks_by_entity == {}


def test_llm_assessor_stage_sends_one_surviving_source_per_llm_request() -> None:
    search_results = [
        make_search_result(
            url=f"https://news.example.com/company-{index}",
            title=f"Company {index} raises funding",
            snippet=f"Company {index} appears in industry coverage.",
            domain="news.example.com",
            rank=index,
        )
        for index in range(1, 8)
    ]
    brave_context_output = make_brave_context_output(
        passages_by_url={
            result.url: [
                make_brave_context_passage(
                    source_url=str(result.url),
                    passage_text=f"{result.title}. More details about company {index}.",
                    metadata={"title": result.title},
                )
            ]
            for index, result in enumerate(search_results, start=1)
        }
    )
    fake_client = BatchAwareFakeAssessorClient()
    assessor = LlmSourceAssessorStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = assessor.run(
        planner_output=make_planner_output(),
        searcher_output=make_searcher_output(
            raw_results=search_results,
            shortlisted_results=search_results,
        ),
        brave_context_output=brave_context_output,
        extractor_light_output=make_extractor_light_output(
            candidate_names=[f"Company {index}" for index in range(1, 8)],
            name_to_source_urls={},
            mention_counts={f"Company {index}": 1 for index in range(1, 8)},
        ),
    )

    assert len(fake_client.calls) == 7
    assert [len(json.loads(call["user_content"])["sources"]) for call in fake_client.calls] == [1] * 7
    assert len(output.assessed_sources) == 7
    assert all(source.filtered_out is False for source in output.assessed_sources)
