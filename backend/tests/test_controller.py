from __future__ import annotations

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BudgetState,
    ChunkRankingOutput,
    EvidenceItem,
    EvidenceStore,
    ExtractedEntity,
    FieldValue,
    ExtractorLightOutput,
    ExtractorOutput,
    PipelineRequest,
    PlannerOutput,
    RetrievedSourcesOutput,
    SearcherOutput,
)
from backend.app.helpers import (
    FinalLogger,
    PlaceholderBraveContextFetcher,
    PlaceholderEvidenceStoreBuilder,
)
from backend.app.orchestrator import PipelineOrchestrator
from backend.app.stages import (
    PlaceholderCanonicalizerVerifierEvaluatorStage,
    PlaceholderExtractorLightStage,
    PlaceholderExtractorStage,
    PlaceholderPlannerStage,
    PlaceholderSearcherStage,
    PlaceholderSourceAssessorStage,
)


class RepairPlanner(PlaceholderPlannerStage):
    def run(self, query: str) -> PlannerOutput:
        return PlannerOutput(
            entity_type="company",
            query_mode="topic_entity_discovery",
            schema_columns=["name", "website"],
            core_aspects=["identity"],
            base_query=query,
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query=query,
        )


class RepairSearcher(PlaceholderSearcherStage):
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def run(
        self,
        planner_output: PlannerOutput,
        followup_queries: list[str] | None = None,
        max_search_queries: int | None = None,
    ) -> SearcherOutput:
        output = super().run(
            planner_output,
            followup_queries=followup_queries,
            max_search_queries=max_search_queries,
        )
        self.calls.append(output.executed_queries)
        return output


class RewriteHeavyPlanner(PlaceholderPlannerStage):
    def run(self, query: str) -> PlannerOutput:
        return PlannerOutput(
            entity_type="company",
            query_mode="topic_entity_discovery",
            schema_columns=["name", "website"],
            core_aspects=["identity"],
            base_query=query,
            initial_query_rewrites=["rewrite 1", "rewrite 2", "rewrite 3"],
            is_topic_query=True,
            normalized_query=query,
        )


class NoopBraveContextFetcher(PlaceholderBraveContextFetcher):
    def run(
        self,
        searcher_output: SearcherOutput,
    ) -> RetrievedSourcesOutput:
        _ = searcher_output
        return RetrievedSourcesOutput(url_sources=[])


class NoopExtractorLight(PlaceholderExtractorLightStage):
    def run(
        self,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput,
    ) -> ExtractorLightOutput:
        _ = planner_output
        _ = chunk_ranking_output
        return ExtractorLightOutput(candidate_names=[], name_to_source_urls={}, mention_counts={})


class NoopAssessor(PlaceholderSourceAssessorStage):
    def run(
        self,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        extractor_light_output: ExtractorLightOutput,
        retrieved_sources_output: RetrievedSourcesOutput | None = None,
        pass_type: AssessorPass = AssessorPass.FIRST_PASS,
        evidence_store: EvidenceStore | None = None,
        remaining_fetch_budget: int = 0,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> AssessorOutput:
        _ = planner_output
        _ = searcher_output
        _ = retrieved_sources_output
        _ = extractor_light_output
        _ = pass_type
        _ = evidence_store
        _ = remaining_fetch_budget
        _ = brave_context_output
        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[],
            verification_gaps=[],
            selected_jina_urls=[],
        )


class NoopEvidenceStoreBuilder(PlaceholderEvidenceStoreBuilder):
    def run(
        self,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        chunk_ranking_output: ChunkRankingOutput | None = None,
        brave_context_output: RetrievedSourcesOutput | None = None,
        existing_store: EvidenceStore | None = None,
    ) -> EvidenceStore:
        _ = chunk_ranking_output
        _ = brave_context_output
        _ = extractor_light_output
        _ = assessor_output
        return existing_store or EvidenceStore(chunks_by_entity={})


class NoopExtractor(PlaceholderExtractorStage):
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
        return prior_output or ExtractorOutput(entities=[])


class RecordingFinalLogger(FinalLogger):
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def log_summary(
        self,
        *,
        request_id: str,
        planner_output: PlannerOutput,
        chunk_ranking_output: ChunkRankingOutput | None,
        extractor_light_output: ExtractorLightOutput | None,
        extractor_output: ExtractorOutput | None,
        finalizer_output,
    ) -> None:
        self.calls.append(
            {
                "request_id": request_id,
                "normalized_query": planner_output.normalized_query,
                "chunk_ranking_output": chunk_ranking_output,
                "extractor_light_output": extractor_light_output,
                "extractor_output": extractor_output,
                "finalizer_output": finalizer_output,
            }
        )


def test_controller_runs_single_retrieval_round_without_repair() -> None:
    searcher = RepairSearcher()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=searcher,
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-1"))

    assert response.repair_used is False
    assert response.budget.used_repair_rounds == 0
    assert response.budget.used_search_rounds == 1
    assert searcher.calls == [["open source database tools"]]


def test_orchestrator_caps_initial_search_queries_to_remaining_budget() -> None:
    searcher = RepairSearcher()
    orchestrator = PipelineOrchestrator(
        planner=RewriteHeavyPlanner(),
        searcher=searcher,
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        budget_factory=lambda: BudgetState(max_total_search_queries=2),
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-2"))

    assert response.budget.used_search_queries == 2
    assert searcher.calls == [["open source database tools", "rewrite 1"]]


def test_orchestrator_logs_final_summary_once() -> None:
    final_logger = RecordingFinalLogger()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=RepairSearcher(),
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        final_logger=final_logger,
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-3"))

    assert response.request_id == "test-3"
    assert len(final_logger.calls) == 1
    assert final_logger.calls[0]["request_id"] == "test-3"
    assert final_logger.calls[0]["normalized_query"] == "open source database tools"


def test_default_final_logger_includes_initial_entity_columns() -> None:
    from backend.app.helpers.final_logger import DefaultFinalLogger

    logger = DefaultFinalLogger()
    evidence = [
        EvidenceItem(
            source_url="https://example.com",
            source_title="Example",
            supporting_snippet="Snippet",
        )
    ]
    extractor_output = ExtractorOutput(
        entities=[
            ExtractedEntity(
                candidate_id="1",
                entity_name="Acme",
                fields={
                    "name": FieldValue(value="Acme", confidence=1.0, evidence=evidence),
                    "website": FieldValue(value="https://acme.example", confidence=1.0, evidence=evidence),
                    "price_range": FieldValue(value=None, confidence=0.0, evidence=[]),
                },
                source_urls=[],
            )
        ]
    )
    assert logger._populated_extracted_columns(extractor_output) == ["name", "website"]
