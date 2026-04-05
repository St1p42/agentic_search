from __future__ import annotations

"""FastAPI shell for request/response and SSE streaming endpoints."""

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.config import (
    load_assessor_runtime_config,
    load_brave_context_runtime_config,
    load_extractor_runtime_config,
    load_extractor_light_runtime_config,
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
    ExtractorOutput,
    JinaFetcherOutput,
    PipelineRequest,
    PipelineResponse,
    PlannerOutput,
    SearcherOutput,
    CanonicalizerVerifierEvaluatorOutput,
)
from backend.app.helpers import build_brave_context_fetcher, build_jina_fetcher
from backend.app.helpers import build_evidence_store_builder
from backend.app.orchestrator import PipelineOrchestrator
from backend.app.stages import (
    ThinFinalizerStage,
    build_extractor_light_stage,
    build_extractor_stage,
    build_planner_stage,
    build_searcher_stage,
    build_source_assessor_stage,
)


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


class ExtractorLightTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    brave_context_output: BraveContextOutput


class JinaFetcherTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessor_output: AssessorOutput
    remaining_fetch_budget: int = Field(default=0, ge=0)


class ExtractorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    extractor_light_output: ExtractorLightOutput
    evidence_store: EvidenceStore


class EvidenceStoreTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brave_context_output: BraveContextOutput
    extractor_light_output: ExtractorLightOutput
    assessor_output: AssessorOutput
    evidence_store: EvidenceStore | None = None


class FinalizerTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    extractor_output: ExtractorOutput


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

@app.post("/api/v1/brave-context/test", response_model=BraveContextOutput)
def run_brave_context_test(searcher_output: SearcherOutput) -> BraveContextOutput:
    brave_context_config = load_brave_context_runtime_config()
    brave_context_fetcher = build_brave_context_fetcher(
        runtime_config=brave_context_config,
    )
    return brave_context_fetcher.run(searcher_output=searcher_output)


@app.post("/api/v1/extractor-light/test", response_model=ExtractorLightOutput)
def run_extractor_light_test(request: ExtractorLightTestRequest) -> ExtractorLightOutput:
    extractor_light_config = load_extractor_light_runtime_config()
    extractor_light = build_extractor_light_stage(runtime_config=extractor_light_config)
    return extractor_light.run(
        planner_output=request.planner_output,
        brave_context_output=request.brave_context_output,
    )


@app.post("/api/v1/assessor/test", response_model=AssessorOutput)
def run_assessor_test(request: AssessorTestRequest) -> AssessorOutput:
    assessor_config = load_assessor_runtime_config()
    assessor = build_source_assessor_stage(runtime_config=assessor_config)
    return assessor.run(
        planner_output=request.planner_output,
        searcher_output=request.searcher_output,
        brave_context_output=request.brave_context_output,
        extractor_light_output=request.extractor_light_output,
        pass_type=request.pass_type,
        evidence_store=request.evidence_store,
        remaining_fetch_budget=request.remaining_fetch_budget,
    )


@app.post("/api/v1/evidence-store/test", response_model=EvidenceStore)
def run_evidence_store_test(request: EvidenceStoreTestRequest) -> EvidenceStore:
    evidence_store_builder = build_evidence_store_builder()
    return evidence_store_builder.run(
        brave_context_output=request.brave_context_output,
        extractor_light_output=request.extractor_light_output,
        assessor_output=request.assessor_output,
        existing_store=request.evidence_store,
    )


@app.post("/api/v1/extractor/test", response_model=ExtractorOutput)
def run_extractor_test(request: ExtractorTestRequest) -> ExtractorOutput:
    extractor_config = load_extractor_runtime_config()
    extractor = build_extractor_stage(runtime_config=extractor_config)
    return extractor.run(
        planner_output=request.planner_output,
        extractor_light_output=request.extractor_light_output,
        evidence_store=request.evidence_store,
    )


@app.post("/api/v1/finalizer/test", response_model=CanonicalizerVerifierEvaluatorOutput)
def run_finalizer_test(request: FinalizerTestRequest) -> CanonicalizerVerifierEvaluatorOutput:
    finalizer = ThinFinalizerStage()
    return finalizer.run(
        planner_output=request.planner_output,
        extractor_output=request.extractor_output,
    )


@app.post("/api/v1/jina-fetcher/test", response_model=JinaFetcherOutput)
def run_jina_fetcher_test(request: JinaFetcherTestRequest) -> JinaFetcherOutput:
    jina_fetcher_config = load_jina_fetcher_runtime_config()
    jina_fetcher = build_jina_fetcher(runtime_config=jina_fetcher_config)
    return jina_fetcher.run(
        assessor_output=request.assessor_output,
        remaining_fetch_budget=request.remaining_fetch_budget,
    )
