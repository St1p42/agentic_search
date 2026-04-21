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
    RetrievedChunk,
    RetrievedSourcesOutput,
    SearchResultItem,
    SearcherOutput,
    UrlSource,
)
from backend.app.helpers import (
    BreadthV2QueryBundle,
    ColumnAwareChunkRankingOutput,
    ColumnFacet,
    ColumnFacetOutput,
    ColumnQuery,
    EntityGapFillResult,
    EntityGapFillUpdate,
    GapFillMerger,
    RankedColumnChunk,
    EntityRankingResult,
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
        entity_ranking_result=None,
    ) -> ExtractorOutput:
        _ = planner_output
        _ = extractor_light_output
        _ = evidence_store
        _ = entity_ranking_result
        return prior_output or ExtractorOutput(entities=[])


class FixedExtractor(PlaceholderExtractorStage):
    def run(
        self,
        planner_output: PlannerOutput,
        extractor_light_output: ExtractorLightOutput,
        evidence_store: EvidenceStore,
        prior_output: ExtractorOutput | None = None,
        entity_ranking_result=None,
    ) -> ExtractorOutput:
        _ = planner_output
        _ = extractor_light_output
        _ = evidence_store
        _ = prior_output
        _ = entity_ranking_result
        evidence = [
            EvidenceItem(
                source_url="https://acme.example/about",
                source_title="Acme",
                supporting_snippet="Acme is a company.",
            )
        ]
        return ExtractorOutput(
            entities=[
                ExtractedEntity(
                    candidate_id="acme",
                    entity_name="Acme",
                    fields={
                        "name": FieldValue(value="Acme", confidence=1.0, evidence=evidence),
                        "website": FieldValue(value=None, confidence=0.0, evidence=[]),
                    },
                    source_urls=[],
                )
            ]
        )


class SpyFacetGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *, normalized_query: str, base_query: str, sparse_columns: list[str]) -> ColumnFacetOutput:
        _ = normalized_query
        _ = base_query
        self.calls += 1
        return ColumnFacetOutput(
            facets=[ColumnFacet(column=column, facet_terms=[column]) for column in sparse_columns]
        )


class FixedSparseColumnDetector:
    def detect(self, *, schema_columns: list[str], extractor_output: ExtractorOutput | None):
        _ = schema_columns
        _ = extractor_output
        from backend.app.helpers import SparseColumnSummary

        return SparseColumnSummary(sparse_columns=["website"], fill_rate_by_column={"website": 0.0})


class FixedBreadthV2QueryBuilder:
    def build(
        self,
        *,
        normalized_query: str,
        facet_output: ColumnFacetOutput,
        max_queries: int,
    ) -> BreadthV2QueryBundle:
        _ = normalized_query
        _ = facet_output
        _ = max_queries
        return BreadthV2QueryBundle(column_queries=[ColumnQuery(column="website", query="acme website")])


class FixedBreadthV2Searcher:
    def run(self, *, planner_output: PlannerOutput, queries: list[str]) -> SearcherOutput:
        _ = planner_output
        result = SearchResultItem(
            url="https://acme.example",
            title="Acme Official Site",
            snippet="Official Acme homepage.",
            domain="acme.example",
            rank=1,
            query_sources=list(queries),
        )
        return SearcherOutput(
            executed_queries=queries,
            raw_results=[result],
            shortlisted_results=[result],
        )


class FixedJinaFetcher:
    def run(
        self,
        searcher_output: SearcherOutput,
        fetch_budget: int = 0,
        request_query: str | None = None,
        planner_output: PlannerOutput | None = None,
    ) -> RetrievedSourcesOutput:
        _ = searcher_output
        _ = fetch_budget
        _ = request_query
        _ = planner_output
        return RetrievedSourcesOutput(
            url_sources=[
                UrlSource(
                    source_id="jina:https://acme.example",
                    url="https://acme.example",
                    title="Acme Official Site",
                    origin="jina",
                    chunks=[
                        RetrievedChunk(
                            chunk_id="jina:https://acme.example#0",
                            source_id="jina:https://acme.example",
                            text="Acme official website is https://acme.example",
                            sequence_index=0,
                        )
                    ],
                )
            ]
        )


class FixedColumnAwareChunkRanker:
    def run(
        self,
        *,
        normalized_query: str,
        extracted_entities: list[ExtractedEntity],
        sparse_columns: list[str],
        facet_output: ColumnFacetOutput,
        url_sources: list[UrlSource],
    ) -> ColumnAwareChunkRankingOutput:
        _ = normalized_query
        _ = extracted_entities
        _ = sparse_columns
        _ = facet_output
        return ColumnAwareChunkRankingOutput(
            url_sources=url_sources,
            ranked_chunks=[
                RankedColumnChunk(
                    entity_name="Acme",
                    column="website",
                    chunk_id="jina:https://acme.example#0",
                    source_id="jina:https://acme.example",
                    score=0.9,
                    rank=1,
                )
            ],
        )


class FixedGapFiller:
    def run(
        self,
        *,
        planner_output: PlannerOutput,
        extractor_output: ExtractorOutput,
        ranking_output: ColumnAwareChunkRankingOutput,
    ) -> EntityGapFillResult:
        _ = planner_output
        _ = extractor_output
        _ = ranking_output
        evidence = [
            EvidenceItem(
                source_url="https://acme.example",
                source_title="Acme Official Site",
                supporting_snippet="Acme official website is https://acme.example",
            )
        ]
        return EntityGapFillResult(
            updates=[
                EntityGapFillUpdate(
                    entity_name="Acme",
                    fields={
                        "website": FieldValue(
                            value="https://acme.example",
                            confidence=0.95,
                            evidence=evidence,
                        )
                    },
                )
            ],
            fields_filled=1,
        )


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
        entity_ranking_result: EntityRankingResult | None,
        extractor_output: ExtractorOutput | None,
        finalizer_output,
        breadth_v2_debug: dict[str, object] | None = None,
    ) -> None:
        self.calls.append(
            {
                "request_id": request_id,
                "normalized_query": planner_output.normalized_query,
                "chunk_ranking_output": chunk_ranking_output,
                "extractor_light_output": extractor_light_output,
                "entity_ranking_result": entity_ranking_result,
                "extractor_output": extractor_output,
                "finalizer_output": finalizer_output,
                "breadth_v2_debug": breadth_v2_debug,
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
    assert isinstance(final_logger.calls[0]["entity_ranking_result"], EntityRankingResult)


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


def test_default_final_logger_emits_breadth_v2_debug_summary(caplog) -> None:
    from backend.app.helpers.final_logger import DefaultFinalLogger

    logger = DefaultFinalLogger()
    planner_output = RepairPlanner().run("open source database tools")

    with caplog.at_level("WARNING"):
        logger.log_summary(
            request_id="debug-1",
            planner_output=planner_output,
            chunk_ranking_output=None,
            extractor_light_output=None,
            entity_ranking_result=None,
            extractor_output=None,
            finalizer_output=None,
            breadth_v2_debug={
                "sparse_columns": ["website"],
                "facet_terms_by_column": {"website": ["official site", "homepage"]},
                "queries": [{"column": "website", "query": "open source database tools official site homepage"}],
                "top_shortlisted_chunks": [
                    {
                        "entity_name": "Acme",
                        "column": "website",
                        "rank": 1,
                        "score": 0.9,
                        "source_url": "https://acme.example",
                        "source_title": "Acme",
                    }
                ],
            },
        )

    messages = [record.message for record in caplog.records]
    assert any(message.startswith("pipeline_debug_summary ") for message in messages)
    assert any(message.startswith("breadth_v2_debug_summary ") for message in messages)


def test_orchestrator_skips_breadth_v2_when_no_entities_extracted() -> None:
    facet_generator = SpyFacetGenerator()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=RepairSearcher(),
        brave_context_fetcher=NoopBraveContextFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        extractor=NoopExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        column_facet_generator=facet_generator,
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-4"))

    assert response.request_id == "test-4"
    assert facet_generator.calls == 0


def test_orchestrator_runs_breadth_v2_and_merges_gap_fills() -> None:
    final_logger = RecordingFinalLogger()
    orchestrator = PipelineOrchestrator(
        planner=RepairPlanner(),
        searcher=RepairSearcher(),
        brave_context_fetcher=NoopBraveContextFetcher(),
        jina_fetcher=FixedJinaFetcher(),
        extractor_light=NoopExtractorLight(),
        assessor=NoopAssessor(),
        evidence_store_builder=NoopEvidenceStoreBuilder(),
        extractor=FixedExtractor(),
        finalizer=PlaceholderCanonicalizerVerifierEvaluatorStage(),
        final_logger=final_logger,
        sparse_column_detector=FixedSparseColumnDetector(),
        column_facet_generator=SpyFacetGenerator(),
        breadth_v2_query_builder=FixedBreadthV2QueryBuilder(),
        breadth_v2_searcher=FixedBreadthV2Searcher(),
        column_aware_chunk_ranker=FixedColumnAwareChunkRanker(),
        entity_gap_filler=FixedGapFiller(),
        gap_fill_merger=GapFillMerger(),
    )

    response = orchestrator.run(PipelineRequest(query="open source database tools", request_id="test-5"))

    assert response.request_id == "test-5"
    extractor_output = final_logger.calls[0]["extractor_output"]
    assert isinstance(extractor_output, ExtractorOutput)
    assert extractor_output.entities[0].fields["website"].value == "https://acme.example"
    breadth_v2_debug = final_logger.calls[0]["breadth_v2_debug"]
    assert breadth_v2_debug is not None
    assert breadth_v2_debug["sparse_columns"] == ["website"]
    assert breadth_v2_debug["facet_terms_by_column"] == {"website": ["website"]}
    assert breadth_v2_debug["queries"] == [{"column": "website", "query": "acme website"}]
    assert breadth_v2_debug["top_shortlisted_chunks"][0]["column"] == "website"
    assert "text" not in breadth_v2_debug["top_shortlisted_chunks"][0]
