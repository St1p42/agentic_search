from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.contracts import PipelineRequest
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
