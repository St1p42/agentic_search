from __future__ import annotations

from backend.app.contracts import (
    AssessedSource,
    AssessorPass,
    BraveContextPassage,
    BraveContextOutput,
    ExtractorLightOutput,
    HeuristicSourceSignals,
    OfficialityLevel,
    PlannerOutput,
    SearchResultItem,
    SourceQuality,
    SourceRole,
)
from backend.app.stages.assessor.llm_source_assessor import AssessorSourceDecision
from backend.app.stages.assessor.models import HeuristicSourceAssessment
from backend.app.stages.assessor.utils import has_official_path, tokenize


def build_heuristic_signals(
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

    relevance_hint = safe_ratio(len(query_tokens & result_tokens), len(query_tokens))
    domain_match_hint = max(
        (
            safe_ratio(
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


def build_assessed_source(
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
        filtered_officiality = heuristic_assessment.officiality.officiality
        if filtered_officiality is None:
            filtered_officiality = OfficialityLevel.THIRD_PARTY
        return AssessedSource(
            result=result,
            brave_context_passages=brave_context_passages,
            heuristic_signals=heuristic_signals,
            source_role=SourceRole.DISCOVERY,
            source_quality=heuristic_assessment.quality.quality,
            officiality=filtered_officiality,
            estimated_aspect_coverage=[],
            evidence_sufficiency=0.0,
            should_deep_fetch=False,
            fetch_reason=heuristic_assessment.filter_reason,
            filtered_out=True,
        )

    source_role = decision.source_role if decision else fallback_source_role(heuristic_signals)
    source_quality = decision.source_quality if decision else heuristic_assessment.quality.quality
    officiality = (
        decision.officiality
        if decision
        else heuristic_assessment.officiality.officiality or fallback_officiality(heuristic_signals)
    )
    aspect_coverage = normalize_aspect_coverage(
        decision.estimated_aspect_coverage if decision else [],
        planner_output=planner_output,
    )
    evidence_sufficiency = (
        decision.evidence_sufficiency
        if decision
        else max(0.1, 1.0 - heuristic_signals.snippet_thinness_hint)
    )
    evidence_sufficiency = apply_evidence_sufficiency_caps(
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


def fallback_source_role(heuristic_signals: HeuristicSourceSignals) -> SourceRole:
    if heuristic_signals.official_path_hint >= 1.0 or heuristic_signals.domain_match_hint >= 0.75:
        return SourceRole.VERIFICATION
    if heuristic_signals.relevance_hint >= 0.25:
        return SourceRole.CORROBORATION
    return SourceRole.DISCOVERY


def fallback_officiality(heuristic_signals: HeuristicSourceSignals) -> OfficialityLevel:
    if heuristic_signals.official_path_hint >= 1.0 and heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.OFFICIAL
    if heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.NEAR_OFFICIAL
    return OfficialityLevel.THIRD_PARTY


def normalize_aspect_coverage(
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


def apply_evidence_sufficiency_caps(
    evidence_sufficiency: float,
    *,
    brave_context_passages: list[BraveContextPassage],
) -> float:
    if not brave_context_passages:
        return min(evidence_sufficiency, 0.5)

    if all(bool(passage.metadata.get("fallback")) for passage in brave_context_passages):
        return min(evidence_sufficiency, 0.55)

    return evidence_sufficiency


def safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))
