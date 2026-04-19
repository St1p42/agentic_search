from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import DEFAULT_ASSESSOR_MODEL, AssessorRuntimeConfig, load_assessor_runtime_config
from backend.app.contracts import (
    AssessorPass,
    HeuristicSourceSignals,
    PlannerOutput,
    RetrievedSourcesOutput,
    SearchResultItem,
    SourceQuality,
    SourceRole,
    OfficialityLevel,
)
from backend.app.prompts import ASSESSOR_SYSTEM_PROMPT
from backend.app.stages.assessor.models import HeuristicSourceAssessment


MAX_ASSESSMENT_PASSAGES_PER_URL = 3
MAX_ASSESSMENT_PASSAGE_CHARS = 800
MAX_CONCURRENT_ASSESSOR_REQUESTS = 4


class AssessorSourceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: str
    source_role: SourceRole = SourceRole.DISCOVERY
    source_quality: SourceQuality = SourceQuality.MEDIUM
    officiality: OfficialityLevel = OfficialityLevel.THIRD_PARTY
    estimated_aspect_coverage: list[str] = Field(default_factory=list)
    evidence_sufficiency: float = Field(default=0.5, ge=0.0, le=1.0)


class AssessorModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessed_sources: list[AssessorSourceDecision] = Field(default_factory=list)


class LlmSourceAssessor:
    def __init__(
        self,
        model: str = DEFAULT_ASSESSOR_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: AssessorRuntimeConfig | None = None,
    ) -> None:
        self.model = model
        self._llm_client = llm_client
        self._runtime_config = runtime_config

    def assess(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
        retrieved_sources_output: RetrievedSourcesOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
        pass_type: AssessorPass,
    ) -> dict[str, AssessorSourceDecision]:
        if not search_results:
            return {}

        max_workers = min(MAX_CONCURRENT_ASSESSOR_REQUESTS, len(search_results))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            outputs = executor.map(
                lambda result: self._assess_one(
                    planner_output=planner_output,
                    search_result=result,
                    retrieved_sources_output=retrieved_sources_output,
                    heuristic_signals_by_url=heuristic_signals_by_url,
                    heuristic_assessments_by_url=heuristic_assessments_by_url,
                    pass_type=pass_type,
                ),
                search_results,
            )
            return {
                str(source_assessment.source_url): source_assessment
                for output in outputs
                for source_assessment in output.assessed_sources
            }

    def _assess_one(
        self,
        *,
        planner_output: PlannerOutput,
        search_result: SearchResultItem,
        retrieved_sources_output: RetrievedSourcesOutput,
        heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
        heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
        pass_type: AssessorPass,
    ) -> AssessorModelOutput:
        return self._client().parse(
            model=self.model,
            system_prompt=ASSESSOR_SYSTEM_PROMPT,
            user_content=_build_assessor_payload(
                planner_output=planner_output,
                search_results=[search_result],
                retrieved_sources_output=retrieved_sources_output,
                heuristic_signals_by_url=heuristic_signals_by_url,
                heuristic_assessments_by_url=heuristic_assessments_by_url,
                pass_type=pass_type,
            ),
            response_model=AssessorModelOutput,
        )

    def _client(self) -> StructuredLlmClient:
        if self._llm_client is not None:
            return self._llm_client

        assessor_config = self._runtime_config or load_assessor_runtime_config()
        if not assessor_config.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is missing from the environment")

        self.model = self.model or assessor_config.model
        self._llm_client = OpenAiStructuredLlmClient(api_key=assessor_config.openai_api_key)
        return self._llm_client


def _build_assessor_payload(
    *,
    planner_output: PlannerOutput,
    search_results: list[SearchResultItem],
    retrieved_sources_output: RetrievedSourcesOutput,
    heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
    heuristic_assessments_by_url: dict[HttpUrl, HeuristicSourceAssessment],
    pass_type: AssessorPass,
) -> str:
    source_payload = []
    for result in search_results:
        heuristic_assessment = heuristic_assessments_by_url[result.url]
        source_payload.append(
            {
                "source_url": str(result.url),
                "title": result.title,
                "snippet": result.snippet,
                "domain": result.domain,
                "rank": result.rank,
                "query_sources": result.query_sources,
                "heuristics": heuristic_signals_by_url[result.url].model_dump(mode="json"),
                "heuristic_quality": heuristic_assessment.quality.quality.value,
                "heuristic_quality_confidence": heuristic_assessment.quality.confidence,
                "heuristic_quality_reasons": heuristic_assessment.quality.reasons,
                "heuristic_officiality": (
                    heuristic_assessment.officiality.officiality.value
                    if heuristic_assessment.officiality.officiality is not None
                    else "ambiguous"
                ),
                "heuristic_officiality_confidence": heuristic_assessment.officiality.confidence,
                "heuristic_officiality_reasons": heuristic_assessment.officiality.reasons,
                "passages": [
                    chunk.text[:MAX_ASSESSMENT_PASSAGE_CHARS]
                    for chunk in _chunks_for_result(retrieved_sources_output, result.url)[
                        :MAX_ASSESSMENT_PASSAGES_PER_URL
                    ]
                    if chunk.text.strip()
                ],
            }
        )

    return json.dumps(
        {
            "pass_type": pass_type.value,
            "entity_type": planner_output.entity_type,
            "normalized_query": planner_output.normalized_query,
            "schema_columns": planner_output.schema_columns,
            "core_aspects": planner_output.core_aspects,
            "sources": source_payload,
        },
        ensure_ascii=True,
    )


def _chunks_for_result(retrieved_sources_output: RetrievedSourcesOutput, source_url: HttpUrl):
    for url_source in retrieved_sources_output.url_sources:
        if url_source.url == source_url:
            return url_source.chunks
    return []
