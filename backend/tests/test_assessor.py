from __future__ import annotations

from typing import cast

from pydantic import HttpUrl

from backend.app.api_clients.llm_client import StructuredLlmClient, StructuredOutputT
from backend.app.contracts import AssessorPass, OfficialityLevel, SourceQuality, SourceRole
from backend.app.stages.source_assessor import (
    AssessorModelOutput,
    AssessorSourceDecision,
    LlmSourceAssessorStage,
)
from backend.tests.fixtures.factories import (
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


def _as_structured_client(fake_client: FakeAssessorClient) -> StructuredLlmClient:
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
