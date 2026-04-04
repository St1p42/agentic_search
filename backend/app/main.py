from __future__ import annotations

"""FastAPI shell for request/response and SSE streaming endpoints."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.config import (
    load_assessor_runtime_config,
    load_brave_context_runtime_config,
    load_jina_fetcher_runtime_config,
    load_planner_runtime_config,
    load_searcher_runtime_config,
)
from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    EvidenceStore,
    ExtractorLightOutput,
    JinaFetcherOutput,
    PipelineRequest,
    PipelineResponse,
    PlannerOutput,
    SearcherOutput,
)
from backend.app.helpers import build_brave_context_fetcher, build_jina_fetcher
from backend.app.orchestrator import PipelineOrchestrator
from backend.app.stages import build_assessor_stage, build_planner_stage, build_searcher_stage


app = FastAPI(title="Agentic Search", version="0.1.0")
orchestrator = PipelineOrchestrator()


class AssessorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    searcher_output: SearcherOutput
    brave_context_output: BraveContextOutput
    extractor_light_output: ExtractorLightOutput
    pass_type: AssessorPass = AssessorPass.FIRST_PASS
    evidence_store: EvidenceStore | None = None
    remaining_fetch_budget: int = Field(default=0, ge=0)


class JinaFetcherTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessor_output: AssessorOutput
    remaining_fetch_budget: int = Field(default=0, ge=0)


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

@app.post("/api/v1/planner/test", response_model=PlannerOutput)
def run_planner_test(request: PipelineRequest) -> PlannerOutput:
    planner_config = load_planner_runtime_config()
    planner = build_planner_stage(runtime_config=planner_config)
    return planner.run(request.query)


@app.post("/api/v1/searcher/test", response_model=SearcherOutput)
def run_searcher_test(planner_output: PlannerOutput) -> SearcherOutput:
    searcher_config = load_searcher_runtime_config()
    searcher = build_searcher_stage(runtime_config=searcher_config)
    return searcher.run(planner_output=planner_output)
