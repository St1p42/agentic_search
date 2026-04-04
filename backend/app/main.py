from __future__ import annotations

"""FastAPI shell for request/response and SSE streaming endpoints."""

from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse

from backend.app.contracts import PipelineRequest, PipelineResponse
from backend.app.orchestrator import PipelineOrchestrator


app = FastAPI(title="Agentic Search", version="0.1.0")
orchestrator = PipelineOrchestrator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/search", response_model=PipelineResponse)
def run_search(request: PipelineRequest) -> PipelineResponse:
    return orchestrator.run(request)


@app.get("/api/v1/search/stream")
def stream_search(query: str, request_id: str | None = None) -> EventSourceResponse:
    request = PipelineRequest(query=query, request_id=request_id)

    def event_generator():
        for event in orchestrator.stream(request):
            yield {
                "event": event.event.value,
                "data": event.model_dump_json(),
            }

    return EventSourceResponse(event_generator())
