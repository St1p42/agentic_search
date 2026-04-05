from __future__ import annotations

"""Deterministic pipeline orchestrator with one bounded repair round."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from queue import Queue
from threading import Thread
from typing import Callable, TypeVar
from uuid import uuid4

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    BudgetState,
    CanonicalizerVerifierEvaluatorOutput,
    ErrorCode,
    EventPayload,
    EvidenceStore,
    ExtractorLightOutput,
    ExtractorOutput,
    JinaFetcherOutput,
    PipelineError,
    PipelineRequest,
    PipelineResponse,
    PlannerOutput,
    RepairDiagnostics,
    SearcherOutput,
    SseEvent,
    SseEventName,
    StageName,
)
from backend.app.event_emitter import PipelineEventEmitter
from backend.app.helpers import (
    BraveContextFetcher,
    DefaultEvidenceStoreBuilder,
    EvidenceStoreBuilder,
    JinaFetcher,
    PlaceholderBraveContextFetcher,
    PlaceholderJinaFetcher,
)
from backend.app.helpers.output_merger import DefaultOutputMerger, OutputMerger
from backend.app.stages import (
    CanonicalizerVerifierEvaluatorStage,
    ExtractorLightStage,
    ExtractorStage,
    PlaceholderCanonicalizerVerifierEvaluatorStage,
    PlaceholderExtractorLightStage,
    PlaceholderExtractorStage,
    PlaceholderPlannerStage,
    PlaceholderSearcherStage,
    PlannerStage,
    SearcherStage,
    PlaceholderSourceAssessorStage,
    SourceAssessorStage,
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
    brave_context_output: BraveContextOutput | None = None
    extractor_light_output: ExtractorLightOutput | None = None
    assessor_output: AssessorOutput | None = None
    evidence_store: EvidenceStore = field(default_factory=EvidenceStore)
    jina_fetcher_output: JinaFetcherOutput | None = None
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
        evidence_store_builder: EvidenceStoreBuilder | None = None,
        jina_fetcher: JinaFetcher | None = None,
        output_merger: OutputMerger | None = None,
        budget_factory: Callable[[], BudgetState] | None = None,
        event_emitter: PipelineEventEmitter | None = None,
    ) -> None:
        self.planner = planner or PlaceholderPlannerStage()
        self.searcher = searcher or PlaceholderSearcherStage()
        self.extractor_light = extractor_light or PlaceholderExtractorLightStage()
        self.assessor = assessor or PlaceholderSourceAssessorStage()
        self.extractor = extractor or PlaceholderExtractorStage()
        self.finalizer = finalizer or PlaceholderCanonicalizerVerifierEvaluatorStage()
        self.brave_context_fetcher = brave_context_fetcher or PlaceholderBraveContextFetcher()
        self.evidence_store_builder = evidence_store_builder or DefaultEvidenceStoreBuilder()
        self.jina_fetcher = jina_fetcher or PlaceholderJinaFetcher()
        self.output_merger = output_merger or DefaultOutputMerger()
        self.budget_factory = budget_factory or BudgetState
        self.event_emitter = event_emitter or PipelineEventEmitter()

    def run(self, request: PipelineRequest) -> PipelineResponse:
        request_id = request.request_id or str(uuid4())
        planner_output = self._run_stage(
            request_id=request_id,
            stage_name=StageName.PLANNER,
            message="planning query and schema",
            action=lambda: self.planner.run(request.query),
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
        diagnostics = state.finalizer_output.diagnostics if state.finalizer_output else None

        if self._repair_allowed(state, diagnostics):
            state.repair_used = True
            state.budget.used_repair_rounds += 1
            self.event_emitter.repair_started(
                request_id=state.request_id,
                followup_queries=diagnostics.suggested_followup_queries,
            )
            self._run_retrieval_pass(
                state,
                followup_queries=diagnostics.suggested_followup_queries,
            )

        return PipelineResponse(
            request_id=state.request_id,
            original_query=state.original_query,
            normalized_query=state.normalized_query,
            normalization_note=state.normalization_note,
            inferred_schema=state.planner_output.schema_columns,
            final_top_10_rows=(state.finalizer_output.final_rows if state.finalizer_output else []),
            diagnostics=state.finalizer_output.diagnostics,
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
                message="pipeline run started",
                data={"query": request.query},
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
            evidence_store_builder=self.evidence_store_builder,
            jina_fetcher=self.jina_fetcher,
            output_merger=self.output_merger,
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
                            message="pipeline run completed",
                            data=response.model_dump(mode="json"),
                            error=None,
                        ),
                    )
                )
            except Exception as exc:
                if isinstance(exc, ValueError):
                    error_code = ErrorCode.INVALID_QUERY
                    error_stage = StageName.PLANNER.value
                else:
                    error_code = ErrorCode.INTERNAL_ERROR
                    error_stage = None
                event_queue.put(
                    SseEvent(
                        event=SseEventName.RUN_FAILED,
                        payload=EventPayload(
                            request_id=request_id,
                            stage=error_stage,
                            message="pipeline run failed",
                            data={},
                            error=PipelineError(
                                code=error_code,
                                message=str(exc),
                                stage=error_stage,
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
            message="running Brave search",
            action=lambda: self.searcher.run(
                state.planner_output,
                followup_queries=followup_queries,
                max_search_queries=self._remaining_search_query_budget(state),
            ),
        )
        state.budget.used_search_rounds += 1
        state.budget.used_search_queries += len(state.searcher_output.executed_queries)

        state.brave_context_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="fetching Brave LLM Context",
            action=lambda: self.brave_context_fetcher.run(state.searcher_output),
        )
        state.extractor_light_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.EXTRACTOR_LIGHT,
            message="extracting candidate names",
            action=lambda: self.extractor_light.run(
                planner_output=state.planner_output,
                brave_context_output=state.brave_context_output,
            ),
        )

        remaining_fetch_budget = max(0, state.budget.max_deep_fetches - state.budget.used_deep_fetches)
        state.assessor_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message="assessing first-pass sources",
            action=lambda: self.assessor.run(
                planner_output=state.planner_output,
                searcher_output=state.searcher_output,
                brave_context_output=state.brave_context_output,
                extractor_light_output=state.extractor_light_output,
                pass_type=AssessorPass.FIRST_PASS,
                evidence_store=state.evidence_store,
                remaining_fetch_budget=remaining_fetch_budget,
            ),
        )

        verification_queries = self._select_verification_queries(state.assessor_output, state.budget)
        if verification_queries:
            self._run_verification_subpass(
                state=state,
                verification_queries=verification_queries,
                remaining_fetch_budget=remaining_fetch_budget,
            )

        self._build_and_merge_evidence_store(state=state, jina_fetcher_output=None)
        self._run_jina_selection_and_fetch(state=state, remaining_fetch_budget=remaining_fetch_budget)
        self._build_and_merge_evidence_store(
            state=state,
            jina_fetcher_output=state.jina_fetcher_output,
            message="merging Jina evidence into evidence store",
        )

        state.extractor_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.EXTRACTOR,
            message="extracting structured entities",
            action=lambda: self.extractor.run(
                planner_output=state.planner_output,
                extractor_light_output=state.extractor_light_output,
                evidence_store=state.evidence_store,
                prior_output=state.extractor_output,
            ),
        )
        state.finalizer_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.CANONICALIZER_VERIFIER_EVALUATOR,
            message="canonicalizing and evaluating final rows",
            action=lambda: self.finalizer.run(
                planner_output=state.planner_output,
                extractor_output=state.extractor_output,
            ),
        )

    def _run_verification_subpass(
        self,
        state: PipelineState,
        verification_queries: list[str],
        remaining_fetch_budget: int,
    ) -> None:
        verification_searcher_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="running bounded verification queries",
            action=lambda: self.searcher.run(
                state.planner_output,
                followup_queries=verification_queries,
                max_search_queries=len(verification_queries),
            ),
        )
        state.budget.used_verification_queries += len(verification_queries)

        verification_brave_context_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.SEARCHER,
            message="fetching Brave LLM Context for verification URLs",
            action=lambda: self.brave_context_fetcher.run(verification_searcher_output),
        )
        verification_assessor_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message="assessing verification URLs",
            action=lambda: self.assessor.run(
                planner_output=state.planner_output,
                searcher_output=verification_searcher_output,
                brave_context_output=verification_brave_context_output,
                extractor_light_output=state.extractor_light_output,
                pass_type=AssessorPass.VERIFICATION_PASS,
                evidence_store=state.evidence_store,
                remaining_fetch_budget=remaining_fetch_budget,
            ),
        )
        state.searcher_output = self.output_merger.merge_searcher_outputs(
            state.searcher_output,
            verification_searcher_output,
        )
        state.brave_context_output = self.output_merger.merge_brave_context_outputs(
            state.brave_context_output,
            verification_brave_context_output,
        )
        state.assessor_output = self.output_merger.merge_assessor_outputs(
            state.assessor_output,
            verification_assessor_output,
        )

    def _build_and_merge_evidence_store(
        self,
        state: PipelineState,
        jina_fetcher_output: JinaFetcherOutput | None,
        message: str = "building entity evidence store",
    ) -> None:
        state.evidence_store = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message=message,
            action=lambda: self.evidence_store_builder.run(
                brave_context_output=state.brave_context_output,
                extractor_light_output=state.extractor_light_output,
                assessor_output=state.assessor_output,
                jina_fetcher_output=jina_fetcher_output,
                existing_store=state.evidence_store,
            ),
        )

    def _run_jina_selection_and_fetch(
        self,
        state: PipelineState,
        remaining_fetch_budget: int,
    ) -> None:
        jina_selection_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message="selecting Jina fetches",
            action=lambda: self.assessor.run(
                planner_output=state.planner_output,
                searcher_output=state.searcher_output,
                brave_context_output=state.brave_context_output,
                extractor_light_output=state.extractor_light_output,
                pass_type=AssessorPass.JINA_SELECTION,
                evidence_store=state.evidence_store,
                remaining_fetch_budget=remaining_fetch_budget,
            ),
        )
        state.assessor_output = self.output_merger.merge_assessor_outputs(
            state.assessor_output,
            jina_selection_output,
        )
        if remaining_fetch_budget <= 0:
            state.jina_fetcher_output = JinaFetcherOutput(fetched_documents=[])
            return
        state.jina_fetcher_output = self._run_stage(
            request_id=state.request_id,
            stage_name=StageName.ASSESSOR,
            message="fetching selected Jina pages",
            action=lambda: self.jina_fetcher.run(
                assessor_output=jina_selection_output,
                remaining_fetch_budget=remaining_fetch_budget,
            ),
        )
        state.budget.used_deep_fetches += len(state.jina_fetcher_output.fetched_documents)

    def _run_stage(
        self,
        request_id: str,
        stage_name: StageName,
        message: str,
        action: Callable[[], StageResultT],
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
        )
        return result

    @staticmethod
    def _repair_allowed(
        state: PipelineState,
        diagnostics: RepairDiagnostics | None,
    ) -> bool:
        if diagnostics is None:
            return False
        if state.repair_used or not state.budget.can_repair:
            return False
        if not diagnostics.repair_recommended or not diagnostics.suggested_followup_queries:
            return False
        return state.budget.can_search

    @staticmethod
    def _select_verification_queries(
        assessor_output: AssessorOutput,
        budget: BudgetState,
    ) -> list[str]:
        if not budget.can_verify:
            return []
        remaining = max(0, budget.max_verification_queries - budget.used_verification_queries)
        ordered_gaps = sorted(
            assessor_output.verification_gaps,
            key=lambda gap: gap.mention_count,
            reverse=True,
        )

        selected_queries: list[str] = []
        seen_queries: set[str] = set()
        for gap in ordered_gaps:
            normalized_query = " ".join(gap.suggested_query.split()).strip()
            if not normalized_query or normalized_query in seen_queries:
                continue
            seen_queries.add(normalized_query)
            selected_queries.append(normalized_query)
            if len(selected_queries) >= remaining:
                break
        return selected_queries
