from __future__ import annotations

"""FastAPI shell for request/response and SSE streaming endpoints."""

from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from sse_starlette.sse import EventSourceResponse

from backend.app.config import (
    load_assessor_runtime_config,
    load_breadth_v2_runtime_config,
    load_brave_context_runtime_config,
    load_extractor_runtime_config,
    load_extractor_light_runtime_config,
    load_jina_fetcher_runtime_config,
    load_planner_runtime_config,
    load_retrieval_runtime_config,
    load_searcher_runtime_config,
)
from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    ChunkRankingOutput,
    EvidenceStore,
    ExtractorLightOutput,
    ExtractorOutput,
    PipelineRequest,
    PipelineResponse,
    PlannerOutput,
    RetrievedSourcesOutput,
    SearcherOutput,
    CanonicalizerVerifierEvaluatorOutput,
)
from backend.app.helpers import (
    BreadthV2SearchConfig,
    BreadthV2Searcher,
    DefaultBreadthV2QueryBuilder,
    DefaultChunkRanker,
    DefaultColumnAwareChunkRanker,
    DefaultColumnFacetGenerator,
    DefaultEntityGapFiller,
    DefaultFinalLogger,
    DefaultSparseColumnDetector,
    GapFillMerger,
    build_brave_context_fetcher,
    build_jina_fetcher,
)
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
DEMO_HTML_PATH = Path(__file__).with_name("templates") / "demo.html"


@lru_cache(maxsize=1)
def get_orchestrator() -> PipelineOrchestrator:
    planner_config = load_planner_runtime_config()
    searcher_config = load_searcher_runtime_config()
    retrieval_config = load_retrieval_runtime_config()
    brave_context_config = load_brave_context_runtime_config()
    extractor_light_config = load_extractor_light_runtime_config()
    assessor_config = load_assessor_runtime_config()
    extractor_config = load_extractor_runtime_config()
    jina_fetcher_config = load_jina_fetcher_runtime_config()
    breadth_v2_config = load_breadth_v2_runtime_config()

    return PipelineOrchestrator(
        planner=build_planner_stage(runtime_config=planner_config),
        searcher=build_searcher_stage(runtime_config=searcher_config),
        brave_context_fetcher=build_brave_context_fetcher(runtime_config=brave_context_config),
        jina_fetcher=build_jina_fetcher(runtime_config=jina_fetcher_config),
        chunk_ranker=DefaultChunkRanker(top_k=retrieval_config.top_k),
        retrieval_mode=retrieval_config.mode,
        extractor_light=build_extractor_light_stage(runtime_config=extractor_light_config),
        assessor=build_source_assessor_stage(runtime_config=assessor_config),
        evidence_store_builder=build_evidence_store_builder(),
        final_logger=DefaultFinalLogger(),
        extractor=build_extractor_stage(runtime_config=extractor_config),
        finalizer=ThinFinalizerStage(),
        breadth_v2_config=breadth_v2_config,
        sparse_column_detector=DefaultSparseColumnDetector(),
        column_facet_generator=DefaultColumnFacetGenerator(openai_api_key=planner_config.openai_api_key),
        breadth_v2_query_builder=DefaultBreadthV2QueryBuilder(),
        breadth_v2_searcher=BreadthV2Searcher(
            runtime_config=searcher_config,
            search_config=BreadthV2SearchConfig(
                sources_per_query=breadth_v2_config.sources_per_query,
                shortlist_cap=breadth_v2_config.shortlist_cap,
            ),
        ),
        column_aware_chunk_ranker=DefaultColumnAwareChunkRanker(),
        entity_gap_filler=DefaultEntityGapFiller(openai_api_key=extractor_config.openai_api_key),
        gap_fill_merger=GapFillMerger(),
    )


class AssessorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    searcher_output: SearcherOutput
    retrieved_sources_output: RetrievedSourcesOutput
    extractor_light_output: ExtractorLightOutput
    pass_type: AssessorPass = AssessorPass.FIRST_PASS
    evidence_store: EvidenceStore | None = None
    remaining_fetch_budget: int = Field(default=0, ge=0)


class ExtractorLightTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    chunk_ranking_output: ChunkRankingOutput


class JinaFetcherTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    searcher_output: SearcherOutput
    fetch_budget: int = Field(default=0, ge=0)
    request_query: str | None = None
    planner_output: PlannerOutput | None = None


class ExtractorTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    extractor_light_output: ExtractorLightOutput
    evidence_store: EvidenceStore


class EvidenceStoreTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_ranking_output: ChunkRankingOutput
    extractor_light_output: ExtractorLightOutput
    assessor_output: AssessorOutput
    evidence_store: EvidenceStore | None = None


class FinalizerTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planner_output: PlannerOutput
    extractor_output: ExtractorOutput


@lru_cache(maxsize=1)
def load_demo_html() -> str:
    return DEMO_HTML_PATH.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/demo", response_class=HTMLResponse)
def demo() -> HTMLResponse:
    return HTMLResponse(load_demo_html())


@app.get("/api/v1/search", response_model=PipelineResponse)
def run_search(query: str, request_id: str | None = None) -> PipelineResponse:
    orchestrator = get_orchestrator()
    return orchestrator.run(PipelineRequest(query=query, request_id=request_id))


@app.post("/api/v1/search", response_model=PipelineResponse)
def run_search_post(request: PipelineRequest) -> PipelineResponse:
    orchestrator = get_orchestrator()
    return orchestrator.run(request)


@app.get("/api/v1/search/stream")
def stream_search(query: str, request_id: str | None = None) -> EventSourceResponse:
    orchestrator = get_orchestrator()
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

@app.post("/api/v1/brave-context/test", response_model=RetrievedSourcesOutput)
def run_brave_context_test(searcher_output: SearcherOutput) -> RetrievedSourcesOutput:
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
        chunk_ranking_output=request.chunk_ranking_output,
    )


@app.post("/api/v1/assessor/test", response_model=AssessorOutput)
def run_assessor_test(request: AssessorTestRequest) -> AssessorOutput:
    assessor_config = load_assessor_runtime_config()
    assessor = build_source_assessor_stage(runtime_config=assessor_config)
    return assessor.run(
        planner_output=request.planner_output,
        searcher_output=request.searcher_output,
        retrieved_sources_output=request.retrieved_sources_output,
        extractor_light_output=request.extractor_light_output,
        pass_type=request.pass_type,
        evidence_store=request.evidence_store,
        remaining_fetch_budget=request.remaining_fetch_budget,
    )


@app.post("/api/v1/evidence-store/test", response_model=EvidenceStore)
def run_evidence_store_test(request: EvidenceStoreTestRequest) -> EvidenceStore:
    evidence_store_builder = build_evidence_store_builder()
    return evidence_store_builder.run(
        chunk_ranking_output=request.chunk_ranking_output,
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


@app.post("/api/v1/jina-fetcher/test", response_model=RetrievedSourcesOutput)
def run_jina_fetcher_test(request: JinaFetcherTestRequest) -> RetrievedSourcesOutput:
    jina_fetcher_config = load_jina_fetcher_runtime_config()
    jina_fetcher = build_jina_fetcher(runtime_config=jina_fetcher_config)
    return jina_fetcher.run(
        searcher_output=request.searcher_output,
        fetch_budget=request.fetch_budget,
        request_query=request.request_query,
        planner_output=request.planner_output,
    )
