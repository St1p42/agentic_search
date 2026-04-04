from __future__ import annotations

from typing import cast

from pydantic import HttpUrl

from backend.app.api_clients.llm_client import StructuredLlmClient, StructuredOutputT
from backend.app.contracts import (
    AssessorPass,
    BraveContextOutput,
    BraveContextPassage as ContractBraveContextPassage,
    EvidenceChunk,
    EvidenceOrigin,
    EvidenceStore,
    ExtractorLightOutput,
    OfficialityLevel,
    PlannerOutput,
    SearchResultItem,
    SearcherOutput,
    SourceQuality,
    SourceRole,
)
from backend.app.stages.assessor import (
    AssessorModelOutput,
    AssessorSourceDecision,
    LlmAssessorStage,
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


def _planner_output() -> PlannerOutput:
    return PlannerOutput(
        entity_type="startup",
        query_mode="topic_entity_discovery",
        schema_columns=["name", "website", "location", "focus_area"],
        core_aspects=["focus_area", "location"],
        base_query="AI startups in healthcare",
        initial_query_rewrites=[],
        is_topic_query=True,
        normalized_query="AI startups in healthcare",
    )


def _search_result(
    *,
    url: str,
    title: str,
    snippet: str,
    domain: str,
    rank: int = 1,
) -> SearchResultItem:
    return SearchResultItem(
        url=HttpUrl(url),
        title=title,
        snippet=snippet,
        domain=domain,
        rank=rank,
        query_sources=["AI startups in healthcare"],
        result_type="search_result",
        provider_metadata={"source": "brave_web_search"},
    )


def _extractor_light_output() -> ExtractorLightOutput:
    return ExtractorLightOutput(
        candidate_names=["Acme Health", "Beta AI"],
        name_to_source_urls={
            "Acme Health": [HttpUrl("https://acmehealth.com/about")],
            "Beta AI": [HttpUrl("https://roundup.example.com/beta-ai")],
        },
        mention_counts={"Acme Health": 4, "Beta AI": 2},
    )


def _as_structured_client(fake_client: FakeAssessorClient) -> StructuredLlmClient:
    return cast(StructuredLlmClient, cast(object, fake_client))


def test_llm_assessor_stage_detects_verification_gaps_and_selects_jina_urls() -> None:
    official_result = _search_result(
        url="https://acmehealth.com/about",
        title="About Acme Health",
        snippet="Acme Health builds clinical AI systems.",
        domain="acmehealth.com",
        rank=1,
    )
    roundup_result = _search_result(
        url="https://roundup.example.com/beta-ai",
        title="Top Healthcare AI Startups",
        snippet="Beta AI appears in a third-party startup roundup.",
        domain="roundup.example.com",
        rank=2,
    )
    searcher_output = SearcherOutput(
        executed_queries=["AI startups in healthcare"],
        raw_results=[official_result, roundup_result],
        shortlisted_results=[official_result, roundup_result],
    )
    brave_context_output = BraveContextOutput(
        passages_by_url={
            official_result.url: [
                ContractBraveContextPassage(
                    source_url=official_result.url,
                    passage_text="Acme Health develops clinical AI in Boston.",
                    metadata={"title": "About Acme Health"},
                )
            ],
            roundup_result.url: [
                ContractBraveContextPassage(
                    source_url=roundup_result.url,
                    passage_text="Beta AI is mentioned in a list of healthcare startups.",
                    metadata={"title": "Top Healthcare AI Startups"},
                )
            ],
        }
    )
    assessor = LlmAssessorStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(
            FakeAssessorClient(
                AssessorModelOutput(
                    assessed_sources=[
                        AssessorSourceDecision(
                            source_url=official_result.url,
                            source_role=SourceRole.VERIFICATION,
                            source_quality=SourceQuality.HIGH,
                            officiality=OfficialityLevel.OFFICIAL,
                            estimated_aspect_coverage=["focus_area", "location"],
                            evidence_sufficiency=0.9,
                        ),
                        AssessorSourceDecision(
                            source_url=roundup_result.url,
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
        planner_output=_planner_output(),
        searcher_output=searcher_output,
        brave_context_output=brave_context_output,
        extractor_light_output=_extractor_light_output(),
        pass_type=AssessorPass.FIRST_PASS,
    )

    assert [gap.entity_name for gap in first_pass_output.verification_gaps] == ["Beta AI"]
    assert first_pass_output.verification_gaps[0].suggested_query == (
        '"Beta AI" startup focus_area location official'
    )
    assert first_pass_output.assessed_sources[0].source_role == SourceRole.VERIFICATION
    assert first_pass_output.assessed_sources[1].estimated_aspect_coverage == ["focus_area"]

    jina_output = assessor.run(
        planner_output=_planner_output(),
        searcher_output=searcher_output,
        brave_context_output=brave_context_output,
        extractor_light_output=_extractor_light_output(),
        pass_type=AssessorPass.JINA_SELECTION,
        evidence_store=EvidenceStore(
            chunks_by_entity={
                "Acme Health": [
                    EvidenceChunk(
                        text="Acme Health develops clinical AI.",
                        source_url=official_result.url,
                        source_title="About Acme Health",
                        source_role=SourceRole.VERIFICATION,
                        source_quality=SourceQuality.HIGH,
                        officiality=OfficialityLevel.OFFICIAL,
                        origin=EvidenceOrigin.BRAVE_LLM,
                        aspect_coverage=["focus_area"],
                    )
                ]
            }
        ),
        remaining_fetch_budget=2,
    )

    assert [str(url) for url in jina_output.selected_jina_urls] == [
        "https://acmehealth.com/about",
        "https://roundup.example.com/beta-ai",
    ]
    assert all(source.should_deep_fetch for source in jina_output.assessed_sources)
