from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import HttpUrl

from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    BraveContextPassage,
    DeepFetchedDocument,
    EvidenceStore,
    ExtractedEntity,
    ExtractorLightOutput,
    ExtractorOutput,
    FieldValue,
    HeuristicSourceSignals,
    JinaFetcherOutput,
    OfficialityLevel,
    PipelineRequest,
    PlannerOutput,
    SearchResultItem,
    SearcherOutput,
    SourceQuality,
    SourceRole,
)
from backend.app.main import app
from backend.app.orchestrator import PipelineOrchestrator


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_endpoint_returns_contract_shape() -> None:
    response = client.post("/api/v1/search", json={"query": "AI startups in healthcare"})
    assert response.status_code == 200
    body = response.json()
    assert body["original_query"] == "AI startups in healthcare"
    assert body["normalized_query"] == "AI startups in healthcare"
    assert "inferred_schema" in body
    assert "final_top_10_rows" in body
    assert body["status"] == "completed"


def test_stream_endpoint_emits_stage_lifecycle_events() -> None:
    response = client.get("/api/v1/search/stream", params={"query": "AI startups in healthcare"})
    assert response.status_code == 200
    body = response.text
    assert "run_started" in body
    assert "stage_started" in body
    assert "stage_completed" in body
    assert "run_completed" in body
    assert body.index("stage_started") < body.index("run_completed")


def test_orchestrator_stream_emits_run_failed_on_internal_error() -> None:
    class ExplodingPlanner:
        def run(self, query: str):
            _ = query
            raise RuntimeError("boom")

    orchestrator = PipelineOrchestrator(planner=ExplodingPlanner())

    events = list(orchestrator.stream(request=PipelineRequest(query="AI startups in healthcare")))

    assert events[0].event == "run_started"
    assert events[-1].event == "run_failed"
    assert events[-1].payload.error is not None
    assert events[-1].payload.error.code == "internal_error"


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


def _search_result() -> SearchResultItem:
    return SearchResultItem(
        url=HttpUrl("https://acmehealth.com/about"),
        title="About Acme Health",
        snippet="Acme Health builds clinical AI systems.",
        domain="acmehealth.com",
        rank=1,
        query_sources=["AI startups in healthcare"],
        result_type="search_result",
        provider_metadata={"source": "brave_web_search"},
    )


def _extractor_light_output() -> ExtractorLightOutput:
    return ExtractorLightOutput(
        candidate_names=["Acme Health"],
        name_to_source_urls={"Acme Health": [HttpUrl("https://acmehealth.com/about")]},
        mention_counts={"Acme Health": 1},
    )


def _searcher_output() -> SearcherOutput:
    search_result = _search_result()
    return SearcherOutput(
        executed_queries=["AI startups in healthcare"],
        raw_results=[search_result],
        shortlisted_results=[search_result],
    )


def _brave_context_output() -> BraveContextOutput:
    search_result = _search_result()
    return BraveContextOutput(
        passages_by_url={
            search_result.url: [
                BraveContextPassage(
                    source_url=search_result.url,
                    passage_text=(
                        "Acme Health develops clinical AI systems for hospitals and care teams."
                    ),
                    metadata={"title": "About Acme Health"},
                )
            ]
        }
    )


def _assessor_output() -> AssessorOutput:
    search_result = _search_result()
    brave_context_output = _brave_context_output()
    return AssessorOutput(
        pass_type=AssessorPass.FIRST_PASS,
        assessed_sources=[
            AssessedSource(
                result=search_result,
                brave_context_passages=brave_context_output.passages_by_url[search_result.url],
                heuristic_signals=HeuristicSourceSignals(
                    relevance_hint=1.0,
                    domain_match_hint=1.0,
                    official_path_hint=1.0,
                    snippet_thinness_hint=0.0,
                    rank_hint=1,
                    source_metadata={"hostname": "acmehealth.com"},
                ),
                source_role=SourceRole.VERIFICATION,
                source_quality=SourceQuality.HIGH,
                officiality=OfficialityLevel.OFFICIAL,
                estimated_aspect_coverage=["focus_area"],
                evidence_sufficiency=0.95,
                should_deep_fetch=False,
                fetch_reason=None,
            )
        ],
        verification_gaps=[],
        selected_jina_urls=[],
    )


def _evidence_store() -> EvidenceStore:
    return EvidenceStore(
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
        }
    )


def test_brave_context_test_endpoint_returns_passages(monkeypatch) -> None:
    brave_context_output = _brave_context_output()

    class FakeEndpointBraveContextFetcher:
        def run(self, searcher_output: SearcherOutput) -> BraveContextOutput:
            _ = searcher_output
            return brave_context_output

    monkeypatch.setattr(
        "backend.app.main.build_brave_context_fetcher",
        lambda runtime_config: FakeEndpointBraveContextFetcher(),
    )

    response = client.post(
        "/api/v1/brave-context/test",
        json=_searcher_output().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["passages_by_url"]["https://acmehealth.com/about"][0][
        "passage_text"
    ] == "Acme Health develops clinical AI systems for hospitals and care teams."


def test_extractor_light_test_endpoint_returns_candidate_names(monkeypatch) -> None:
    extractor_light_output = _extractor_light_output()

    class FakeEndpointExtractorLight:
        def run(
            self,
            planner_output: PlannerOutput,
            brave_context_output: BraveContextOutput,
        ) -> ExtractorLightOutput:
            _ = planner_output
            _ = brave_context_output
            return extractor_light_output

    monkeypatch.setattr(
        "backend.app.main.build_extractor_light_stage",
        lambda runtime_config: FakeEndpointExtractorLight(),
    )

    response = client.post(
        "/api/v1/extractor-light/test",
        json={
            "planner_output": _planner_output().model_dump(mode="json"),
            "brave_context_output": _brave_context_output().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["candidate_names"] == ["Acme Health"]


def test_assessor_test_endpoint_returns_assessed_sources(monkeypatch) -> None:
    assessor_output = _assessor_output()

    class FakeEndpointAssessor:
        def run(
            self,
            planner_output: PlannerOutput,
            searcher_output: SearcherOutput,
            brave_context_output: BraveContextOutput,
            extractor_light_output: ExtractorLightOutput,
            pass_type: AssessorPass = AssessorPass.FIRST_PASS,
            evidence_store: EvidenceStore | None = None,
            remaining_fetch_budget: int = 0,
        ) -> AssessorOutput:
            _ = planner_output
            _ = searcher_output
            _ = brave_context_output
            _ = extractor_light_output
            _ = pass_type
            _ = evidence_store
            _ = remaining_fetch_budget
            return assessor_output

    monkeypatch.setattr(
        "backend.app.main.build_source_assessor_stage",
        lambda runtime_config: FakeEndpointAssessor(),
    )

    response = client.post(
        "/api/v1/assessor/test",
        json={
            "planner_output": _planner_output().model_dump(mode="json"),
            "searcher_output": _searcher_output().model_dump(mode="json"),
            "brave_context_output": _brave_context_output().model_dump(mode="json"),
            "extractor_light_output": _extractor_light_output().model_dump(mode="json"),
            "pass_type": "first_pass",
            "evidence_store": None,
            "remaining_fetch_budget": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["assessed_sources"][0]["source_role"] == "verification"


def test_evidence_store_test_endpoint_returns_entity_chunks() -> None:
    response = client.post(
        "/api/v1/evidence-store/test",
        json={
            "brave_context_output": _brave_context_output().model_dump(mode="json"),
            "extractor_light_output": _extractor_light_output().model_dump(mode="json"),
            "assessor_output": _assessor_output().model_dump(mode="json"),
            "evidence_store": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["chunks_by_entity"]["Acme Health"][0]["text"] == (
        "Acme Health develops clinical AI systems for hospitals and care teams."
    )


def test_extractor_test_endpoint_returns_entity_rows(monkeypatch) -> None:
    extractor_output = ExtractorOutput(
        entities=[
            ExtractedEntity(
                candidate_id="Acme Health",
                entity_name="Acme Health",
                fields={
                    "name": FieldValue(
                        value="Acme Health",
                        confidence=1.0,
                        evidence=[
                            {
                                "source_url": "https://acmehealth.com/about",
                                "source_title": "About Acme Health",
                                "supporting_snippet": "Acme Health develops clinical AI systems for hospitals and care teams.",
                                "source_role": "verification",
                                "source_quality": "high",
                                "officiality": "official",
                            }
                        ],
                    ),
                    "website": FieldValue(value=None, confidence=0.0, evidence=[]),
                    "location": FieldValue(value=None, confidence=0.0, evidence=[]),
                    "focus_area": FieldValue(
                        value="clinical AI systems for hospitals and care teams",
                        confidence=0.84,
                        evidence=[
                            {
                                "source_url": "https://acmehealth.com/about",
                                "source_title": "About Acme Health",
                                "supporting_snippet": "Acme Health develops clinical AI systems for hospitals and care teams.",
                                "source_role": "verification",
                                "source_quality": "high",
                                "officiality": "official",
                            }
                        ],
                    ),
                },
                source_urls=[HttpUrl("https://acmehealth.com/about")],
                provisional=False,
            )
        ]
    )

    class FakeEndpointExtractor:
        def run(
            self,
            planner_output: PlannerOutput,
            extractor_light_output: ExtractorLightOutput,
            evidence_store: EvidenceStore,
            prior_output: ExtractorOutput | None = None,
        ) -> ExtractorOutput:
            _ = planner_output
            _ = extractor_light_output
            _ = evidence_store
            _ = prior_output
            return extractor_output

    monkeypatch.setattr(
        "backend.app.main.build_extractor_stage",
        lambda runtime_config: FakeEndpointExtractor(),
    )

    response = client.post(
        "/api/v1/extractor/test",
        json={
            "planner_output": _planner_output().model_dump(mode="json"),
            "extractor_light_output": _extractor_light_output().model_dump(mode="json"),
            "evidence_store": _evidence_store().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["entities"][0]["entity_name"] == "Acme Health"
    assert response.json()["entities"][0]["fields"]["name"]["value"] == "Acme Health"


def test_finalizer_test_endpoint_returns_final_rows() -> None:
    extractor_output = ExtractorOutput(
        entities=[
            ExtractedEntity(
                candidate_id="Acme Health",
                entity_name="Acme Health",
                fields={
                    "name": FieldValue(
                        value="Acme Health",
                        confidence=1.0,
                        evidence=[
                            {
                                "source_url": "https://acmehealth.com/about",
                                "source_title": "About Acme Health",
                                "supporting_snippet": "Acme Health develops clinical AI systems for hospitals and care teams.",
                                "source_role": "verification",
                                "source_quality": "high",
                                "officiality": "official",
                            }
                        ],
                    ),
                    "website": FieldValue(value=None, confidence=0.0, evidence=[]),
                    "location": FieldValue(value=None, confidence=0.0, evidence=[]),
                    "focus_area": FieldValue(
                        value="clinical AI systems",
                        confidence=0.84,
                        evidence=[
                            {
                                "source_url": "https://acmehealth.com/about",
                                "source_title": "About Acme Health",
                                "supporting_snippet": "Acme Health develops clinical AI systems for hospitals and care teams.",
                                "source_role": "verification",
                                "source_quality": "high",
                                "officiality": "official",
                            }
                        ],
                    ),
                },
                source_urls=[HttpUrl("https://acmehealth.com/about")],
                provisional=False,
            )
        ]
    )

    response = client.post(
        "/api/v1/finalizer/test",
        json={
            "planner_output": _planner_output().model_dump(mode="json"),
            "extractor_output": extractor_output.model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["final_rows"][0]["name"] == "Acme Health"
    assert "diagnostics" not in response.json()


def test_jina_fetcher_test_endpoint_returns_fetched_documents(monkeypatch) -> None:
    class FakeEndpointJinaFetcher:
        def run(
            self,
            assessor_output: AssessorOutput,
            remaining_fetch_budget: int,
        ) -> JinaFetcherOutput:
            _ = assessor_output
            _ = remaining_fetch_budget
            return JinaFetcherOutput(
                fetched_documents=[
                    DeepFetchedDocument(
                        url=HttpUrl("https://acmehealth.com/about"),
                        title="Acme Health",
                        text="Acme Health builds clinical AI.",
                        chunks=["Acme Health builds clinical AI."],
                        fetch_succeeded=True,
                        error_message=None,
                    )
                ]
            )

    monkeypatch.setattr(
        "backend.app.main.build_jina_fetcher",
        lambda runtime_config: FakeEndpointJinaFetcher(),
    )

    response = client.post(
        "/api/v1/jina-fetcher/test",
        json={
            "assessor_output": _assessor_output().model_dump(mode="json"),
            "remaining_fetch_budget": 1,
        },
    )

    assert response.status_code == 200
    assert response.json()["fetched_documents"][0]["chunks"] == [
        "Acme Health builds clinical AI."
    ]
