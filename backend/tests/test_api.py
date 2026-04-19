from __future__ import annotations

from fastapi.testclient import TestClient
from pydantic import HttpUrl

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    DeepFetchedDocument,
    EvidenceOrigin,
    EvidenceStore,
    ExtractorLightOutput,
    ExtractorOutput,
    JinaFetcherOutput,
    PipelineRequest,
    PlannerOutput,
    RetrievedChunk,
    SearcherOutput,
    UrlSource,
)
from backend.app.main import app
from backend.app.orchestrator import PipelineOrchestrator
from backend.tests.fixtures.factories import (
    make_assessed_source,
    make_assessor_output,
    make_brave_context_output,
    make_brave_context_passage,
    make_evidence_chunk,
    make_evidence_store,
    make_extracted_entity,
    make_extractor_light_output,
    make_extractor_output,
    make_field_value,
    make_planner_output,
    make_search_result,
    make_searcher_output,
)


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_demo_endpoint_serves_html() -> None:
    response = client.get("/demo")
    assert response.status_code == 200
    assert "Agentic Search Demo" in response.text
    assert "/api/v1/search/stream" in response.text
    assert "EventSource" in response.text


def test_search_endpoint_returns_contract_shape() -> None:
    app.dependency_overrides = {}
    from backend.app.main import get_orchestrator

    app_orchestrator = PipelineOrchestrator()
    original = get_orchestrator
    try:
        import backend.app.main as main_module

        main_module.get_orchestrator.cache_clear()
        main_module.get_orchestrator = lambda: app_orchestrator
        response = client.get("/api/v1/search", params={"query": "AI startups in healthcare"})
    finally:
        import backend.app.main as main_module

        main_module.get_orchestrator = original

    assert response.status_code == 200
    body = response.json()
    assert body["original_query"] == "AI startups in healthcare"
    assert body["normalized_query"] == "AI startups in healthcare"
    assert "inferred_schema" in body
    assert "final_top_10_rows" in body
    assert body["status"] == "completed"


def test_stream_endpoint_emits_stage_lifecycle_events() -> None:
    from backend.app.main import get_orchestrator

    app_orchestrator = PipelineOrchestrator()
    original = get_orchestrator
    try:
        import backend.app.main as main_module

        main_module.get_orchestrator.cache_clear()
        main_module.get_orchestrator = lambda: app_orchestrator
        response = client.get("/api/v1/search/stream", params={"query": "AI startups in healthcare"})
    finally:
        import backend.app.main as main_module

        main_module.get_orchestrator = original

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
    return make_planner_output()


def _searcher_output() -> SearcherOutput:
    search_result = make_search_result()
    return make_searcher_output(
        raw_results=[search_result],
        shortlisted_results=[search_result],
    )


def _brave_context_output() -> BraveContextOutput:
    search_result = make_search_result()
    return make_brave_context_output(
        passages_by_url={
            search_result.url: [
                make_brave_context_passage(
                    source_url=str(search_result.url),
                    passage_text=(
                        "Acme Health develops clinical AI systems for hospitals and care teams."
                    ),
                    metadata={"title": "About Acme Health"},
                )
            ]
        }
    )


def _assessor_output() -> AssessorOutput:
    search_result = make_search_result()
    brave_context_output = _brave_context_output()
    return make_assessor_output(
        assessed_sources=[
            make_assessed_source(
                result=search_result,
                brave_context_passages=brave_context_output.passages_by_url[search_result.url],
            )
        ]
    )


def _evidence_store() -> EvidenceStore:
    return make_evidence_store(chunks_by_entity={"Acme Health": [make_evidence_chunk()]})


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
    extractor_light_output = make_extractor_light_output()

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
            "extractor_light_output": make_extractor_light_output().model_dump(mode="json"),
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
            "extractor_light_output": make_extractor_light_output().model_dump(mode="json"),
            "assessor_output": _assessor_output().model_dump(mode="json"),
            "evidence_store": None,
        },
    )

    assert response.status_code == 200
    assert response.json()["chunks_by_entity"]["Acme Health"][0]["text"] == (
        "Acme Health develops clinical AI systems for hospitals and care teams."
    )


def test_extractor_test_endpoint_returns_entity_rows(monkeypatch) -> None:
    extractor_output = make_extractor_output(
        entities=[
            make_extracted_entity(
                fields={
                    "name": make_field_value(value="Acme Health", confidence=1.0),
                    "website": make_field_value(value=None, confidence=0.0),
                    "location": make_field_value(value=None, confidence=0.0),
                    "focus_area": make_field_value(
                        value="clinical AI systems for hospitals and care teams",
                        confidence=0.84,
                    ),
                }
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
            "extractor_light_output": make_extractor_light_output().model_dump(mode="json"),
            "evidence_store": _evidence_store().model_dump(mode="json"),
        },
    )

    assert response.status_code == 200
    assert response.json()["entities"][0]["entity_name"] == "Acme Health"
    assert response.json()["entities"][0]["fields"]["name"]["value"] == "Acme Health"


def test_finalizer_test_endpoint_returns_final_rows() -> None:
    extractor_output = make_extractor_output(
        entities=[
            make_extracted_entity(
                fields={
                    "name": make_field_value(value="Acme Health", confidence=1.0),
                    "website": make_field_value(value=None, confidence=0.0),
                    "location": make_field_value(value=None, confidence=0.0),
                    "focus_area": make_field_value(
                        value="clinical AI systems",
                        confidence=0.84,
                    ),
                }
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


def test_finalizer_test_endpoint_prunes_name_only_rows() -> None:
    extractor_output = make_extractor_output(
        entities=[
            make_extracted_entity(
                fields={
                    "name": make_field_value(value="Acme Health", confidence=1.0),
                    "website": make_field_value(value=None, confidence=0.0),
                    "location": make_field_value(value=None, confidence=0.0),
                    "focus_area": make_field_value(value=None, confidence=0.0),
                }
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
    assert response.json()["final_rows"] == []


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
                        chunks=[
                            RetrievedChunk(
                                chunk_id="jina:https://acmehealth.com/about#0",
                                source_id="jina:https://acmehealth.com/about",
                                text="Acme Health builds clinical AI.",
                                sequence_index=0,
                            )
                        ],
                        fetch_succeeded=True,
                        error_message=None,
                    )
                ],
                url_sources=[
                    UrlSource(
                        source_id="jina:https://acmehealth.com/about",
                        url=HttpUrl("https://acmehealth.com/about"),
                        title="Acme Health",
                        origin=EvidenceOrigin.JINA,
                        chunks=[
                            RetrievedChunk(
                                chunk_id="jina:https://acmehealth.com/about#0",
                                source_id="jina:https://acmehealth.com/about",
                                text="Acme Health builds clinical AI.",
                                sequence_index=0,
                            )
                        ],
                    )
                ],
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
        {
            "chunk_id": "jina:https://acmehealth.com/about#0",
            "source_id": "jina:https://acmehealth.com/about",
            "text": "Acme Health builds clinical AI.",
            "sequence_index": 0,
        }
    ]
    assert response.json()["url_sources"] == [
        {
            "source_id": "jina:https://acmehealth.com/about",
            "url": "https://acmehealth.com/about",
            "title": "Acme Health",
            "origin": "jina",
            "metadata": {},
            "chunks": [
                {
                    "chunk_id": "jina:https://acmehealth.com/about#0",
                    "source_id": "jina:https://acmehealth.com/about",
                    "text": "Acme Health builds clinical AI.",
                    "sequence_index": 0,
                }
            ],
        }
    ]
