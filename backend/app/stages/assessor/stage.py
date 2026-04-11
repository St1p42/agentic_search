from __future__ import annotations

from typing import Protocol

from backend.app.api_clients import StructuredLlmClient
from backend.app.config import AssessorRuntimeConfig, load_assessor_runtime_config
from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    AssessorPass,
    BraveContextPassage,
    BraveContextOutput,
    EvidenceStore,
    ExtractorLightOutput,
    HeuristicSourceSignals,
    OfficialityLevel,
    PlannerOutput,
    SearchResultItem,
    SearcherOutput,
    SourceQuality,
    SourceRole,
)
from backend.app.stages.assessor.heuristic_source_assessor import HeuristicSourceAssessor
from backend.app.stages.assessor.llm_source_assessor import (
    AssessorSourceDecision,
    LlmSourceAssessor,
)
from backend.app.stages.assessor.models import HeuristicSourceAssessment
from backend.app.stages.assessor.utils import has_official_path, tokenize


class SourceAssessorStage(Protocol):
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
        """Classify shortlisted sources for first-pass downstream extraction."""


class PlaceholderSourceAssessorStage:
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
        _ = evidence_store
        _ = remaining_fetch_budget
        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[],
            verification_gaps=[],
            selected_jina_urls=[],
        )

class LlmSourceAssessorStage:
    def __init__(
        self,
        model: str,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: AssessorRuntimeConfig | None = None,
        heuristic_assessor: HeuristicSourceAssessor | None = None,
    ) -> None:
        self._heuristic_assessor = heuristic_assessor or HeuristicSourceAssessor()
        self._llm_assessor = LlmSourceAssessor(
            model=model,
            llm_client=llm_client,
            runtime_config=runtime_config,
        )

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
        if not searcher_output.shortlisted_results:
            return AssessorOutput(
                pass_type=pass_type,
                assessed_sources=[],
                verification_gaps=[],
                selected_jina_urls=[],
            )

        heuristic_signals_by_url = {
            result.url: _heuristic_signals(
                result=result,
                planner_output=planner_output,
                extractor_light_output=extractor_light_output,
            )
            for result in searcher_output.shortlisted_results
        }
        heuristic_assessments_by_url = {
            result.url: self._heuristic_assessor.assess(
                result=result,
                brave_context_output=brave_context_output,
                heuristic_signals=heuristic_signals_by_url[result.url],
                candidate_names=extractor_light_output.candidate_names,
            )
            for result in searcher_output.shortlisted_results
        }
        llm_results = [
            result
            for result in searcher_output.shortlisted_results
            if not heuristic_assessments_by_url[result.url].filtered_out
        ]
        decisions_by_url = self._llm_assessor.assess(
            planner_output=planner_output,
            search_results=llm_results,
            brave_context_output=brave_context_output,
            heuristic_signals_by_url=heuristic_signals_by_url,
            heuristic_assessments_by_url=heuristic_assessments_by_url,
            pass_type=pass_type,
        )
        _ = evidence_store
        _ = remaining_fetch_budget

        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=[
                _build_assessed_source(
                    result=result,
                    brave_context_output=brave_context_output,
                    heuristic_signals=heuristic_signals_by_url[result.url],
                    heuristic_assessment=heuristic_assessments_by_url[result.url],
                    decision=decisions_by_url.get(str(result.url)),
                    planner_output=planner_output,
                    pass_type=pass_type,
                )
                for result in searcher_output.shortlisted_results
            ],
            verification_gaps=[],
            selected_jina_urls=[],
        )


def build_source_assessor_stage(
    runtime_config: AssessorRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> SourceAssessorStage:
    config = runtime_config or load_assessor_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderSourceAssessorStage()
    if config.mode == "llm":
        return LlmSourceAssessorStage(
            model=config.model,
            llm_client=llm_client,
            runtime_config=config,
        )
    raise ValueError(f"Unsupported assessor mode: {config.mode}")


def _heuristic_signals(
    *,
    result: SearchResultItem,
    planner_output: PlannerOutput,
    extractor_light_output: ExtractorLightOutput,
) -> HeuristicSourceSignals:
    query_tokens = tokenize(
        f"{planner_output.normalized_query} {planner_output.base_query} "
        f"{' '.join(planner_output.core_aspects)}"
    )
    result_tokens = tokenize(f"{result.title} {result.snippet}")
    name_tokens_by_candidate = [
        tokenize(candidate_name)
        for candidate_name in extractor_light_output.candidate_names
        if candidate_name.strip()
    ]

    relevance_hint = _safe_ratio(len(query_tokens & result_tokens), len(query_tokens))
    domain_match_hint = max(
        (
            _safe_ratio(
                len(candidate_tokens & tokenize(result.domain.replace(".", " "))),
                len(candidate_tokens),
            )
            for candidate_tokens in name_tokens_by_candidate
        ),
        default=0.0,
    )
    official_path_hint = 1.0 if has_official_path(str(result.url)) else 0.0
    snippet_thinness_hint = max(
        0.0,
        min(1.0, 1.0 - (len(result.snippet.strip()) / 80)),
    )

    return HeuristicSourceSignals(
        relevance_hint=relevance_hint,
        domain_match_hint=domain_match_hint,
        official_path_hint=official_path_hint,
        snippet_thinness_hint=snippet_thinness_hint,
        rank_hint=result.rank,
        source_metadata={
            "hostname": result.domain,
            "title": result.title,
            "snippet_length": len(result.snippet),
            "result_type": result.result_type,
            **result.provider_metadata,
        },
    )


def _build_assessed_source(
    *,
    result: SearchResultItem,
    brave_context_output: BraveContextOutput,
    heuristic_signals: HeuristicSourceSignals,
    heuristic_assessment: HeuristicSourceAssessment,
    decision: AssessorSourceDecision | None,
    planner_output: PlannerOutput,
    pass_type: AssessorPass,
) -> AssessedSource:
    brave_context_passages = brave_context_output.passages_by_url.get(result.url, [])
    if heuristic_assessment.filtered_out:
        return AssessedSource(
            result=result,
            brave_context_passages=brave_context_passages,
            heuristic_signals=heuristic_signals,
            source_role=SourceRole.DISCOVERY,
            source_quality=heuristic_assessment.quality.quality,
            officiality=heuristic_assessment.officiality.officiality or OfficialityLevel.THIRD_PARTY,
            estimated_aspect_coverage=[],
            evidence_sufficiency=0.0,
            should_deep_fetch=False,
            fetch_reason=heuristic_assessment.filter_reason,
            filtered_out=True,
        )

    source_role = decision.source_role if decision else _fallback_source_role(heuristic_signals)
    source_quality = decision.source_quality if decision else heuristic_assessment.quality.quality
    officiality = (
        decision.officiality
        if decision
        else heuristic_assessment.officiality.officiality or _fallback_officiality(heuristic_signals)
    )
    aspect_coverage = _normalize_aspect_coverage(
        decision.estimated_aspect_coverage if decision else [],
        planner_output=planner_output,
    )
    evidence_sufficiency = (
        decision.evidence_sufficiency
        if decision
        else max(0.1, 1.0 - heuristic_signals.snippet_thinness_hint)
    )
    evidence_sufficiency = _apply_evidence_sufficiency_caps(
        evidence_sufficiency,
        brave_context_passages=brave_context_passages,
    )
    _ = pass_type

    return AssessedSource(
        result=result,
        brave_context_passages=brave_context_passages,
        heuristic_signals=heuristic_signals,
        source_role=source_role,
        source_quality=source_quality,
        officiality=officiality,
        estimated_aspect_coverage=aspect_coverage,
        evidence_sufficiency=evidence_sufficiency,
        should_deep_fetch=False,
        fetch_reason=None,
        filtered_out=False,
    )


def _fallback_source_role(heuristic_signals: HeuristicSourceSignals) -> SourceRole:
    if heuristic_signals.official_path_hint >= 1.0 or heuristic_signals.domain_match_hint >= 0.75:
        return SourceRole.VERIFICATION
    if heuristic_signals.relevance_hint >= 0.25:
        return SourceRole.CORROBORATION
    return SourceRole.DISCOVERY


def _fallback_officiality(heuristic_signals: HeuristicSourceSignals) -> OfficialityLevel:
    if heuristic_signals.official_path_hint >= 1.0 and heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.OFFICIAL
    if heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.NEAR_OFFICIAL
    return OfficialityLevel.THIRD_PARTY


def _normalize_aspect_coverage(
    raw_aspects: list[str],
    *,
    planner_output: PlannerOutput,
) -> list[str]:
    allowed_aspects = {aspect.lower(): aspect for aspect in planner_output.core_aspects}
    normalized_aspects: list[str] = []
    seen_aspects: set[str] = set()
    for aspect in raw_aspects:
        dedupe_key = " ".join(aspect.split()).strip().lower()
        if not dedupe_key or dedupe_key in seen_aspects or dedupe_key not in allowed_aspects:
            continue
        seen_aspects.add(dedupe_key)
        normalized_aspects.append(allowed_aspects[dedupe_key])
    return normalized_aspects


def _apply_evidence_sufficiency_caps(
    evidence_sufficiency: float,
    *,
    brave_context_passages: list[BraveContextPassage],
) -> float:
    if not brave_context_passages:
        return min(evidence_sufficiency, 0.5)

    if all(bool(passage.metadata.get("fallback")) for passage in brave_context_passages):
        return min(evidence_sufficiency, 0.55)

    return evidence_sufficiency


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))
