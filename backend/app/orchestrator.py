from __future__ import annotations

"""Deterministic pipeline orchestrator for the active single-pass flow."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from queue import Queue
from threading import Thread
from typing import Callable, TypeVar
from uuid import uuid4

from backend.app.contracts import (
    AssessingSourceQualityStageUiModel,
    AssessorPass,
    AssessorOutput,
    BuildingEntitiesStageUiModel,
    BudgetState,
    CanonicalizerVerifierEvaluatorOutput,
    ChunkRankingOutput,
    ErrorCode,
    EventPayload,
    EvidenceStore,
    ExtractedEntity,
    ExtractorLightOutput,
    ExtractorOutput,
    FinalizingTableStageUiModel,
    HeuristicAssessingSourceQualityStageUiModel,
    IdentifyingCandidatesStageUiModel,
    OfficialityLevel,
    PipelineError,
    PipelineRequest,
    PipelineResponse,
    PlanningStageUiModel,
    PlannerOutput,
    ProcessingSourcesStageUiModel,
    RetrievedSourcesOutput,
    RetrievingEvidenceStageUiModel,
    RetrievingSourcesStageUiModel,
    SchemaPreviewColumnUiModel,
    SchemaPreviewUiModel,
    SearcherOutput,
    SseEvent,
    SseEventName,
    SourceQuality,
    StageName,
    StageUiDetails,
    StartedSearchStageUiModel,
)
from backend.app.stages.assessor import LlmSourceAssessorStage
from backend.app.event_emitter import PipelineEventEmitter
from backend.app.helpers import (
    BraveContextFetcher,
    ChunkRanker,
    DefaultChunkRanker,
    DefaultEvidenceStoreBuilder,
    EvidenceStoreBuilder,
    JinaFetcher,
    PlaceholderBraveContextFetcher,
    PlaceholderJinaFetcher,
)
from backend.app.stages import (
    CanonicalizerVerifierEvaluatorStage,
    ExtractorLightStage,
    ExtractorStage,
    PlaceholderExtractorLightStage,
    PlaceholderExtractorStage,
    PlaceholderPlannerStage,
    PlaceholderSearcherStage,
    PlannerStage,
    PlaceholderSourceAssessorStage,
    SearcherStage,
    SourceAssessorStage,
    ThinFinalizerStage,
)


StageResultT = TypeVar("StageResultT")


@dataclass
class PipelineState:
    request_id: str
    original_query: str
    normalized_query: str
    normalization_note: str | None
    planner_output: PlannerOutput
    budget: BudgetState
    searcher_output: SearcherOutput | None = None
    retrieved_sources_output: RetrievedSourcesOutput | None = None
    chunk_ranking_output: ChunkRankingOutput | None = None
    extractor_light_output: ExtractorLightOutput | None = None
    assessor_output: AssessorOutput | None = None
    evidence_store: EvidenceStore = field(default_factory=EvidenceStore)
    extractor_output: ExtractorOutput | None = None
    finalizer_output: CanonicalizerVerifierEvaluatorOutput | None = None
    repair_used: bool = False


class PipelineOrchestrator:
    def __init__(
        self,
        planner: PlannerStage | None = None,
        searcher: SearcherStage | None = None,
        extractor_light: ExtractorLightStage | None = None,
        assessor: SourceAssessorStage | None = None,
        extractor: ExtractorStage | None = None,
        finalizer: CanonicalizerVerifierEvaluatorStage | None = None,
        brave_context_fetcher: BraveContextFetcher | None = None,
        jina_fetcher: JinaFetcher | None = None,
        chunk_ranker: ChunkRanker | None = None,
        retrieval_mode: str = "jina",
        evidence_store_builder: EvidenceStoreBuilder | None = None,
        budget_factory: Callable[[], BudgetState] | None = None,
        event_emitter: PipelineEventEmitter | None = None,
    ) -> None:
        self.planner = planner or PlaceholderPlannerStage()
        self.searcher = searcher or PlaceholderSearcherStage()
        self.extractor_light = extractor_light or PlaceholderExtractorLightStage()
        self.assessor = assessor or PlaceholderSourceAssessorStage()
        self.extractor = extractor or PlaceholderExtractorStage()
        self.finalizer = finalizer or ThinFinalizerStage()
        self.brave_context_fetcher = brave_context_fetcher or PlaceholderBraveContextFetcher()
        self.jina_fetcher = jina_fetcher or PlaceholderJinaFetcher()
        self.chunk_ranker = chunk_ranker or DefaultChunkRanker()
        self.retrieval_mode = retrieval_mode
        self.evidence_store_builder = evidence_store_builder or DefaultEvidenceStoreBuilder()
        self.budget_factory = budget_factory or BudgetState
        self.event_emitter = event_emitter or PipelineEventEmitter()

    def run(self, request: PipelineRequest) -> PipelineResponse:
        request_id = request.request_id or str(uuid4())
        planner_output = self._run_stage(
            request_id=request_id,
            stage_name=StageName.PLANNER,
            message="Planning",
            action=lambda: self.planner.run(request.query),
            completed_data_factory=lambda result: _planning_event_data(result),
        )
        if planner_output.error:
            raise ValueError(planner_output.error_message or "planner rejected query")

        state = PipelineState(
            request_id=request_id,
            original_query=request.query,
            normalized_query=planner_output.normalized_query,
            normalization_note=planner_output.normalization_note,
            planner_output=planner_output,
            budget=self.budget_factory(),
        )

        self._run_retrieval_pass(state, followup_queries=None)
        return PipelineResponse(
            request_id=state.request_id,
            original_query=state.original_query,
            normalized_query=state.normalized_query,
            normalization_note=state.normalization_note,
            inferred_schema=state.planner_output.schema_columns,
            final_top_10_rows=(state.finalizer_output.final_rows if state.finalizer_output else []),
            budget=state.budget,
            repair_used=state.repair_used,
            status="completed",
        )

    def stream(self, request: PipelineRequest) -> Iterator[SseEvent]:
        request_id = request.request_id or str(uuid4())
        yield SseEvent(
            event=SseEventName.RUN_STARTED,
            payload=EventPayload(
                request_id=request_id,
                stage=None,
                message="Started search",
                data={
                    "query": request.query,
                    "details": _ui_event_data(StartedSearchStageUiModel(query=request.query).to_ui_details()),
                },
                error=None,
            ),
        )
        event_queue: Queue[SseEvent | None] = Queue()
        streamed_orchestrator = PipelineOrchestrator(
            planner=self.planner,
            searcher=self.searcher,
            extractor_light=self.extractor_light,
            assessor=self.assessor,
            extractor=self.extractor,
            finalizer=self.finalizer,
            brave_context_fetcher=self.brave_context_fetcher,
            jina_fetcher=self.jina_fetcher,
            chunk_ranker=self.chunk_ranker,
            retrieval_mode=self.retrieval_mode,
            evidence_store_builder=self.evidence_store_builder,
            budget_factory=self.budget_factory,
            event_emitter=PipelineEventEmitter(event_queue.put),
        )

        def run_pipeline() -> None:
            try:
                response = streamed_orchestrator.run(
                    PipelineRequest(query=request.query, request_id=request_id),
                )
                event_queue.put(
                    SseEvent(
                        event=SseEventName.RUN_COMPLETED,
                        payload=EventPayload(
                            request_id=response.request_id,
                            stage=None,
                            message="Search completed",
                            data=response.model_dump(mode="json"),
                            error=None,
                        ),
                    )
                )
            except Exception as exc:
                if isinstance(exc, ValueError):
                    error_code = ErrorCode.INVALID_QUERY
                    error_stage = StageName.PLANNER.value
                    error_message = str(exc)
                    error_details: dict[str, str] = {}
                else:
                    error_code = ErrorCode.INTERNAL_ERROR
                    error_stage = None
                    error_message = "Something went wrong while running the research pipeline."
                    error_details = {"internal_exception": str(exc)}
                event_queue.put(
                    SseEvent(
                        event=SseEventName.RUN_FAILED,
                        payload=EventPayload(
                            request_id=request_id,
                            stage=error_stage,
                            message="Search failed",
                            data={},
                            error=PipelineError(
                                code=error_code,
                                message=error_message,
                                stage=error_stage,
                                details=error_details,
                            ),
                        ),
                    )
                )
            finally:
                event_queue.put(None)

        Thread(target=run_pipeline, daemon=True).start()

        while True:
            event = event_queue.get()
            if event is None:
                break
            yield event

    def _remaining_search_query_budget(self, state: PipelineState) -> int:
        return max(
            0,
            state.budget.max_total_search_queries - state.budget.used_search_queries,
        )

    def _run_retrieval_pass(
        self,
        state: PipelineState,
        followup_queries: list[str] | None,
    ) -> None:
        if not state.budget.can_search:
            raise RuntimeError("search budget exhausted")

        state.searcher_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="Retrieving sources",
            action=lambda: self.searcher.run(
                state.planner_output,
                followup_queries=followup_queries,
                max_search_queries=self._remaining_search_query_budget(state),
            ),
            completed_data_factory=lambda result: _ui_event_data(
                RetrievingSourcesStageUiModel(
                    queries_run=len(result.executed_queries),
                    sources_found=len(result.raw_results),
                    shortlisted=len(result.shortlisted_results),
                ).to_ui_details()
            ),
        )
        state.budget.used_search_rounds += 1
        state.budget.used_search_queries += len(state.searcher_output.executed_queries)

        state.retrieved_sources_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="Processing sources",
            action=lambda: self._fetch_retrieved_sources(state),
            completed_data_factory=lambda result: _ui_event_data(
                ProcessingSourcesStageUiModel(
                    sources_processed=len(result.url_sources),
                    relevant_details_found=sum(
                        len([chunk for chunk in source.chunks if chunk.text.strip()])
                        for source in result.url_sources
                    ),
                ).to_ui_details()
            ),
        )
        state.budget.used_deep_fetches += len(state.retrieved_sources_output.url_sources)
        state.chunk_ranking_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="Ranking evidence chunks",
            action=lambda: self.chunk_ranker.run(
                planner_output=state.planner_output,
                url_sources=state.retrieved_sources_output.url_sources,
            ),
        )
        state.extractor_light_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.EXTRACTOR_LIGHT,
            message="Identifying candidates",
            action=lambda: self.extractor_light.run(
                planner_output=state.planner_output,
                chunk_ranking_output=state.chunk_ranking_output,
            ),
            completed_data_factory=lambda result: _ui_event_data(
                IdentifyingCandidatesStageUiModel(
                    preliminary_candidates=len(result.candidate_names),
                    mentions_found=sum(result.mention_counts.values()),
                ).to_ui_details()
            ),
        )

        state.assessor_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message="Assessing source quality",
            action=lambda: self.assessor.run(
                planner_output=state.planner_output,
                searcher_output=state.searcher_output,
                retrieved_sources_output=state.retrieved_sources_output,
                extractor_light_output=state.extractor_light_output,
                pass_type=AssessorPass.FIRST_PASS,
                evidence_store=state.evidence_store,
                remaining_fetch_budget=0,
            ),
            completed_data_factory=lambda result: _ui_event_data(
                _assessor_stage_ui_details(assessor=self.assessor, assessor_output=result)
            ),
        )
        self._build_and_merge_evidence_store(
            state=state,
            completed_data_factory=lambda result: _ui_event_data(
                RetrievingEvidenceStageUiModel(
                    candidates_with_evidence=sum(1 for chunks in result.chunks_by_entity.values() if chunks),
                    supporting_sources_linked=len(
                        {str(chunk.source_url) for chunks in result.chunks_by_entity.values() for chunk in chunks}
                    ),
                ).to_ui_details()
            ),
        )

        state.extractor_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.EXTRACTOR,
            message="Building entities",
            action=lambda: self.extractor.run(
                planner_output=state.planner_output,
                extractor_light_output=state.extractor_light_output,
                evidence_store=state.evidence_store,
                prior_output=state.extractor_output,
            ),
            completed_data_factory=lambda result: _ui_event_data(
                BuildingEntitiesStageUiModel(
                    profiles_built=len(result.entities),
                    missing_fields=_missing_fields_count(result.entities),
                ).to_ui_details()
            ),
        )
        state.finalizer_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.FINALIZER,
            message="Finalizing table",
            action=lambda: self.finalizer.run(
                planner_output=state.planner_output,
                extractor_output=state.extractor_output,
            ),
            completed_data_factory=lambda result: _ui_event_data(
                FinalizingTableStageUiModel(rows_ready=len(result.final_rows)).to_ui_details()
            ),
        )

    def _build_and_merge_evidence_store(
        self,
        state: PipelineState,
        message: str = "Retrieving evidence",
        completed_data_factory: Callable[[EvidenceStore], dict[str, object]] | None = None,
    ) -> None:
        state.evidence_store = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message=message,
            action=lambda: self.evidence_store_builder.run(
                chunk_ranking_output=state.chunk_ranking_output or ChunkRankingOutput(),
                extractor_light_output=state.extractor_light_output,
                assessor_output=state.assessor_output,
                existing_store=state.evidence_store,
            ),
            completed_data_factory=completed_data_factory,
        )

    def _fetch_retrieved_sources(self, state: PipelineState) -> RetrievedSourcesOutput:
        searcher_output = state.searcher_output or SearcherOutput(
            executed_queries=[],
            raw_results=[],
            shortlisted_results=[],
        )
        fetch_budget = max(0, state.budget.max_deep_fetches - state.budget.used_deep_fetches)
        if self.retrieval_mode == "jina":
            return self.jina_fetcher.run(
                searcher_output=searcher_output,
                fetch_budget=fetch_budget,
                request_query=state.original_query,
                planner_output=state.planner_output,
            )
        if self.retrieval_mode == "brave_context":
            return self.brave_context_fetcher.run(searcher_output)
        raise ValueError(f"Unsupported retrieval mode: {self.retrieval_mode}")

    def _run_stage(
        self,
        request_id: str,
        stage_name: StageName,
        message: str,
        action: Callable[[], StageResultT],
        completed_data_factory: Callable[[StageResultT], dict[str, object]] | None = None,
    ) -> StageResultT:
        self.event_emitter.stage_started(
            request_id=request_id,
            stage_name=stage_name,
            message=message,
        )
        result = action()
        self.event_emitter.stage_completed(
            request_id=request_id,
            stage_name=stage_name,
            message=f"{message} completed",
            data=completed_data_factory(result) if completed_data_factory else {},
        )
        return result


def _ui_event_data(details: StageUiDetails) -> dict[str, object]:
    return details.model_dump(mode="json")


def _planning_event_data(planner_output: PlannerOutput) -> dict[str, object]:
    model = PlanningStageUiModel(
        interpreted_query=planner_output.normalized_query,
        columns_selected=len(planner_output.schema_columns),
        schema_preview=_schema_preview_from_planner_output(planner_output),
    )
    return {
        **_ui_event_data(model.to_ui_details()),
        "schema_preview": model.schema_preview.model_dump(mode="json"),
    }


def _sources_kept_for_analysis_count(assessor_output: AssessorOutput) -> int:
    return sum(
        1
        for source in assessor_output.assessed_sources
        if (
            not source.filtered_out
            and source.source_quality != SourceQuality.LOW
            and source.officiality != OfficialityLevel.LOW_QUALITY
        )
    )


def _heuristic_filtered_sources_count(assessor_output: AssessorOutput) -> int:
    return sum(1 for source in assessor_output.assessed_sources if source.filtered_out)


def _sources_sent_to_llm_count(assessor_output: AssessorOutput) -> int:
    return sum(
        1
        for source in assessor_output.assessed_sources
        if not source.filtered_out
    )


def _assessor_stage_ui_details(
    *,
    assessor: object,
    assessor_output: AssessorOutput,
):
    if isinstance(assessor, LlmSourceAssessorStage):
        return AssessingSourceQualityStageUiModel(
            sources_assessed=len(assessor_output.assessed_sources),
            heuristic_filtered_sources=_heuristic_filtered_sources_count(assessor_output),
            sources_sent_to_llm=_sources_sent_to_llm_count(assessor_output),
            sources_kept_for_analysis=_sources_kept_for_analysis_count(assessor_output),
        ).to_ui_details()

    return HeuristicAssessingSourceQualityStageUiModel(
        sources_reviewed=len(assessor_output.assessed_sources),
        filtered_out=_heuristic_filtered_sources_count(assessor_output),
        used_for_evidence=_sources_kept_for_analysis_count(assessor_output),
    ).to_ui_details()


def _missing_fields_count(entities: list[ExtractedEntity]) -> int:
    return sum(
        1
        for entity in entities
        for field_value in entity.fields.values()
        if field_value.value is None
    )


def _schema_preview_from_planner_output(planner_output: PlannerOutput) -> SchemaPreviewUiModel:
    return SchemaPreviewUiModel(
        entity_type=planner_output.entity_type,
        columns=[
            SchemaPreviewColumnUiModel(
                key=column,
                label=column.replace("_", " ").title(),
                type="url" if column in {"website", "url"} or column.endswith("_url") else "text",
            )
            for column in planner_output.schema_columns
        ],
    )
