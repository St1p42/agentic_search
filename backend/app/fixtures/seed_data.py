from __future__ import annotations

"""Representative fixtures that document the shared contract shapes."""

from pydantic import HttpUrl

from backend.app.contracts import (
    BudgetState,
    BraveContextPassage,
    CanonicalEntity,
    EventPayload,
    EvidenceChunk,
    EvidenceItem,
    EvidenceOrigin,
    EvidenceStore,
    FieldValue,
    HeuristicSourceSignals,
    OfficialityLevel,
    PipelineRequest,
    PipelineResponse,
    PlannerOutput,
    RetrievedChunk,
    SourceQuality,
    SourceRole,
    SseEvent,
    SseEventName,
)


EXAMPLE_ABOUT_URL = HttpUrl("https://example.com/about")


EXAMPLE_SEARCH_METADATA = {
    "domain": "example.com",
    "provider_metadata": {"source": "brave_web_search"},
}

EXAMPLE_BRAVE_CONTEXT_PASSAGE = BraveContextPassage(
    source_url=EXAMPLE_ABOUT_URL,
    passage_text="Example Health AI develops AI tooling for clinical workflows.",
    metadata={"retrieval_source": "brave_llm_context"},
)

EXAMPLE_RETRIEVED_CHUNK = RetrievedChunk(
    chunk_id="brave_llm:https://example.com/about#0",
    source_id="brave_llm:https://example.com/about",
    text="Example Health AI develops AI tooling for clinical workflows.",
    sequence_index=0,
)

EXAMPLE_HEURISTIC_SIGNALS = HeuristicSourceSignals(
    relevance_hint=0.9,
    domain_match_hint=0.8,
    official_path_hint=0.9,
    snippet_thinness_hint=0.1,
    rank_hint=1,
    source_metadata={"hostname": "example.com", "result_type": "web"},
)

EXAMPLE_EVIDENCE_STORE = EvidenceStore(
    chunks_by_entity={
        "Example Health AI": [
            EvidenceChunk(
                text="Example Health AI develops AI tooling for clinical workflows.",
                source_url=EXAMPLE_ABOUT_URL,
                source_title="About Example Health AI",
                source_role=SourceRole.VERIFICATION,
                source_quality=SourceQuality.HIGH,
                officiality=OfficialityLevel.OFFICIAL,
                origin=EvidenceOrigin.BRAVE_LLM,
                aspect_coverage=["product"],
            )
        ]
    }
)


SEED_QUERY = PipelineRequest(
    query="AI startups in healthcare",
    request_id="seed-request-001",
)

EXAMPLE_PLANNER_OUTPUT = PlannerOutput(
    entity_type="startup",
    query_mode="topic_entity_discovery",
    schema_columns=["name", "description", "website", "focus_area", "location"],
    core_aspects=["clinical_focus", "product", "market_presence"],
    base_query="AI startups in healthcare",
    initial_query_rewrites=[
        "healthcare AI startups",
        "medical AI startups",
    ],
    is_topic_query=True,
    normalized_query="AI startups in healthcare",
)

EXAMPLE_FINAL_RESPONSE = PipelineResponse(
    request_id="seed-request-001",
    original_query="AI startups in healthcare",
    normalized_query="AI startups in healthcare",
    normalization_note=None,
    inferred_schema=["name", "description", "website", "focus_area", "location"],
    final_top_10_rows=[
        CanonicalEntity(
            name="Example Health AI",
            fields={
                "description": FieldValue(
                    value="Develops AI tooling for clinical workflows",
                    confidence=0.91,
                    evidence=[
                        EvidenceItem(
                            source_url=EXAMPLE_ABOUT_URL,
                            source_title="About Example Health AI",
                            supporting_snippet="Example Health AI develops AI tooling for clinical workflows.",
                            source_role=SourceRole.VERIFICATION,
                            source_quality=SourceQuality.HIGH,
                            officiality=OfficialityLevel.OFFICIAL,
                        )
                    ],
                )
            },
            source_urls=[EXAMPLE_ABOUT_URL],
        )
    ],
    budget=BudgetState(used_search_rounds=1, used_search_queries=3, used_deep_fetches=1),
    repair_used=False,
)

EXAMPLE_SSE_LIFECYCLE = [
    SseEvent(
        event=SseEventName.RUN_STARTED,
        payload=EventPayload(
            request_id="seed-request-001",
            stage=None,
            message="Started search",
            data={"query": "AI startups in healthcare"},
        ),
    ),
    SseEvent(
        event=SseEventName.RUN_COMPLETED,
        payload=EventPayload(
            request_id="seed-request-001",
            stage=None,
            message="Search completed",
            data=EXAMPLE_FINAL_RESPONSE.model_dump(mode="json"),
        ),
    ),
]
