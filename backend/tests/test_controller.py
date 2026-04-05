from __future__ import annotations

from backend.app.contracts import (
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    BudgetState,
    CanonicalizerVerifierEvaluatorOutput,
    EvidenceStore,
    ExtractorLightOutput,
    ExtractorOutput,
    JinaFetcherOutput,
    PipelineRequest,
    PlannerOutput,
    SearcherOutput,
)
from backend.app.helpers import (
    PlaceholderBraveContextFetcher,
    PlaceholderEvidenceStoreBuilder,
    PlaceholderJinaFetcher,
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
    ) -> BraveContextOutput:
        _ = searcher_output
        return BraveContextOutput(passages_by_url={})


class NoopExtractorLight(PlaceholderExtractorLightStage):
    def run(
        self,
        planner_output: PlannerOutput,
        brave_context_output: BraveContextOutput,
    ) -> ExtractorLightOutput:
        _ = planner_output
        _ = brave_context_output
        return ExtractorLightOutput(candidate_names=[], name_to_source_urls={}, mention_counts={})


class NoopAssessor(PlaceholderSourceAssessorStage):
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
        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[],
            verification_gaps=[],
            selected_jina_urls=[],
        )


class NoopEvidenceStoreBuilder(PlaceholderEvidenceStoreBuilder):
    def run(
        self,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        jina_fetcher_output: JinaFetcherOutput | None = None,
        existing_store: EvidenceStore | None = None,
    ) -> EvidenceStore:
        _ = brave_context_output
        _ = extractor_light_output
        _ = assessor_output
        _ = jina_fetcher_output
        return existing_store or EvidenceStore(chunks_by_entity={})


class NoopJinaFetcher(PlaceholderJinaFetcher):
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        _ = assessor_output
        _ = remaining_fetch_budget
        return JinaFetcherOutput(fetched_documents=[])


class CountingJinaFetcher(NoopJinaFetcher):
    def __init__(self) -> None:
        self.calls = 0

    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        self.calls += 1
        return super().run(assessor_output, remaining_fetch_budget)


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


def test_controller_runs_single_retrieval_round_without_repair() -> None:
    searcher = RepairSearcher()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=searcher,
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        jina_fetcher=NoopJinaFetcher(),
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
        jina_fetcher=NoopJinaFetcher(),
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        budget_factory=lambda: BudgetState(max_total_search_queries=2),
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-2"))

    assert response.budget.used_search_queries == 2
    assert searcher.calls == [["open source database tools", "rewrite 1"]]


def test_orchestrator_skips_jina_fetch_when_fetch_budget_is_exhausted() -> None:
    jina_fetcher = CountingJinaFetcher()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=RepairSearcher(),
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        jina_fetcher=jina_fetcher,
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        budget_factory=lambda: BudgetState(max_deep_fetches=0),
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-3"))

    assert response.budget.used_deep_fetches == 0
    assert jina_fetcher.calls == 0
