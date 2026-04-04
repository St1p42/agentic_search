from __future__ import annotations

"""Assessor stage interface and placeholder implementation."""

import json
import re
from typing import Protocol
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.api_clients import OpenAiStructuredLlmClient, StructuredLlmClient
from backend.app.config import (
    DEFAULT_ASSESSOR_MODEL,
    AssessorRuntimeConfig,
    load_assessor_runtime_config,
)
from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    EntityVerificationGap,
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
from backend.app.prompts import ASSESSOR_SYSTEM_PROMPT


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
OFFICIAL_PATH_MARKERS = ("/about", "/company", "/contact", "/team")
THIN_SNIPPET_CHAR_THRESHOLD = 80
MAX_ENTITIES_PER_VERIFICATION_QUERY = 3
MAX_ASSESSMENT_PASSAGES_PER_URL = 3
MAX_ASSESSMENT_PASSAGE_CHARS = 1200
JINA_OFFICIALITY_SCORE = {
    OfficialityLevel.OFFICIAL: 4,
    OfficialityLevel.NEAR_OFFICIAL: 3,
    OfficialityLevel.THIRD_PARTY: 1,
    OfficialityLevel.LOW_QUALITY: 0,
}
JINA_QUALITY_SCORE = {
    SourceQuality.HIGH: 3,
    SourceQuality.MEDIUM: 2,
    SourceQuality.LOW: 0,
}


class AssessorStage(Protocol):
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
        """Classify sources, detect verification gaps, and/or select Jina URLs."""


class PlaceholderAssessorStage:
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


class AssessorSourceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl
    source_role: SourceRole = SourceRole.DISCOVERY
    source_quality: SourceQuality = SourceQuality.MEDIUM
    officiality: OfficialityLevel = OfficialityLevel.THIRD_PARTY
    estimated_aspect_coverage: list[str] = Field(default_factory=list)
    evidence_sufficiency: float = Field(default=0.5, ge=0.0, le=1.0)


class AssessorModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessed_sources: list[AssessorSourceDecision] = Field(default_factory=list)


class LlmAssessorStage:
    def __init__(
        self,
        model: str = DEFAULT_ASSESSOR_MODEL,
        llm_client: StructuredLlmClient | None = None,
        runtime_config: AssessorRuntimeConfig | None = None,
    ) -> None:
        self.model = model
        self._llm_client = llm_client
        self._runtime_config = runtime_config

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
        assessed_sources = self._assess_sources(
            planner_output=planner_output,
            searcher_output=searcher_output,
            brave_context_output=brave_context_output,
            extractor_light_output=extractor_light_output,
            pass_type=pass_type,
        )

        verification_gaps: list[EntityVerificationGap] = []
        selected_jina_urls: list[HttpUrl] = []

        if pass_type == AssessorPass.FIRST_PASS:
            verification_gaps = _detect_verification_gaps(
                assessed_sources=assessed_sources,
                extractor_light_output=extractor_light_output,
                planner_output=planner_output,
            )
        elif pass_type == AssessorPass.JINA_SELECTION:
            selected_jina_urls = _select_jina_urls(
                assessed_sources=assessed_sources,
                evidence_store=evidence_store or EvidenceStore(),
                remaining_fetch_budget=remaining_fetch_budget,
            )

        return AssessorOutput(
            pass_type=pass_type,
            assessed_sources=assessed_sources,
            verification_gaps=verification_gaps,
            selected_jina_urls=selected_jina_urls,
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

    def _assess_sources(
        self,
        *,
        planner_output: PlannerOutput,
        searcher_output: SearcherOutput,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        pass_type: AssessorPass,
    ) -> list[AssessedSource]:
        if not searcher_output.shortlisted_results:
            return []

        heuristic_signals_by_url = {
            result.url: _heuristic_signals(
                result=result,
                planner_output=planner_output,
                extractor_light_output=extractor_light_output,
            )
            for result in searcher_output.shortlisted_results
        }
        model_output = self._client().parse(
            model=self.model,
            system_prompt=ASSESSOR_SYSTEM_PROMPT,
            user_content=_build_assessor_payload(
                planner_output=planner_output,
                searcher_output=searcher_output,
                brave_context_output=brave_context_output,
                extractor_light_output=extractor_light_output,
                heuristic_signals_by_url=heuristic_signals_by_url,
                pass_type=pass_type,
            ),
            response_model=AssessorModelOutput,
        )
        decisions_by_url = {
            str(source_assessment.source_url): source_assessment
            for source_assessment in model_output.assessed_sources
        }

        return [
            _build_assessed_source(
                result=result,
                brave_context_output=brave_context_output,
                heuristic_signals=heuristic_signals_by_url[result.url],
                decision=decisions_by_url.get(str(result.url)),
                planner_output=planner_output,
                pass_type=pass_type,
            )
            for result in searcher_output.shortlisted_results
        ]


def build_assessor_stage(
    runtime_config: AssessorRuntimeConfig | None = None,
    llm_client: StructuredLlmClient | None = None,
) -> AssessorStage:
    config = runtime_config or load_assessor_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderAssessorStage()
    if config.mode == "llm":
        return LlmAssessorStage(
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
    query_tokens = _tokenize(
        f"{planner_output.normalized_query} {planner_output.base_query} "
        f"{' '.join(planner_output.core_aspects)}"
    )
    result_tokens = _tokenize(f"{result.title} {result.snippet}")
    name_tokens_by_candidate = [
        _tokenize(candidate_name)
        for candidate_name in extractor_light_output.candidate_names
        if candidate_name.strip()
    ]

    relevance_hint = _safe_ratio(len(query_tokens & result_tokens), len(query_tokens))
    domain_match_hint = max(
        (
            _safe_ratio(
                len(candidate_tokens & _tokenize(result.domain.replace(".", " "))),
                len(candidate_tokens),
            )
            for candidate_tokens in name_tokens_by_candidate
        ),
        default=0.0,
    )
    official_path_hint = 1.0 if _has_official_path(result.url) else 0.0
    snippet_thinness_hint = max(
        0.0,
        min(1.0, 1.0 - (len(result.snippet.strip()) / THIN_SNIPPET_CHAR_THRESHOLD)),
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


def _build_assessor_payload(
    *,
    planner_output: PlannerOutput,
    searcher_output: SearcherOutput,
    brave_context_output: BraveContextOutput,
    extractor_light_output: ExtractorLightOutput,
    heuristic_signals_by_url: dict[HttpUrl, HeuristicSourceSignals],
    pass_type: AssessorPass,
) -> str:
    source_payload = []
    for result in searcher_output.shortlisted_results:
        source_payload.append(
            {
                "source_url": str(result.url),
                "title": result.title,
                "snippet": result.snippet,
                "domain": result.domain,
                "rank": result.rank,
                "query_sources": result.query_sources,
                "heuristics": heuristic_signals_by_url[result.url].model_dump(mode="json"),
                "passages": [
                    passage.passage_text[:MAX_ASSESSMENT_PASSAGE_CHARS]
                    for passage in brave_context_output.passages_by_url.get(result.url, [])[
                        :MAX_ASSESSMENT_PASSAGES_PER_URL
                    ]
                    if passage.passage_text.strip()
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
            "candidate_names": extractor_light_output.candidate_names,
            "sources": source_payload,
        },
        ensure_ascii=True,
    )


def _build_assessed_source(
    *,
    result: SearchResultItem,
    brave_context_output: BraveContextOutput,
    heuristic_signals: HeuristicSourceSignals,
    decision: AssessorSourceDecision | None,
    planner_output: PlannerOutput,
    pass_type: AssessorPass,
) -> AssessedSource:
    source_role = decision.source_role if decision else _fallback_source_role(heuristic_signals)
    source_quality = decision.source_quality if decision else _fallback_source_quality(heuristic_signals)
    officiality = decision.officiality if decision else _fallback_officiality(heuristic_signals)
    aspect_coverage = _normalize_aspect_coverage(
        decision.estimated_aspect_coverage if decision else [],
        planner_output=planner_output,
    )
    evidence_sufficiency = (
        decision.evidence_sufficiency
        if decision
        else max(0.1, 1.0 - heuristic_signals.snippet_thinness_hint)
    )
    should_deep_fetch = (
        pass_type == AssessorPass.JINA_SELECTION
        and _should_deep_fetch_source(
            source_role=source_role,
            source_quality=source_quality,
            officiality=officiality,
            aspect_coverage=aspect_coverage,
            evidence_sufficiency=evidence_sufficiency,
        )
    )

    return AssessedSource(
        result=result,
        brave_context_passages=brave_context_output.passages_by_url.get(result.url, []),
        heuristic_signals=heuristic_signals,
        source_role=source_role,
        source_quality=source_quality,
        officiality=officiality,
        estimated_aspect_coverage=aspect_coverage,
        evidence_sufficiency=evidence_sufficiency,
        should_deep_fetch=should_deep_fetch,
        fetch_reason=_fetch_reason(
            source_role=source_role,
            source_quality=source_quality,
            officiality=officiality,
            evidence_sufficiency=evidence_sufficiency,
        )
        if should_deep_fetch
        else None,
    )


def _detect_verification_gaps(
    *,
    assessed_sources: list[AssessedSource],
    extractor_light_output: ExtractorLightOutput,
    planner_output: PlannerOutput,
) -> list[EntityVerificationGap]:
    role_by_url = {
        str(assessed_source.result.url): assessed_source.source_role
        for assessed_source in assessed_sources
    }
    ordered_candidate_names = sorted(
        extractor_light_output.candidate_names,
        key=lambda name: extractor_light_output.mention_counts.get(name, 0),
        reverse=True,
    )
    missing_verification_entities = [
        entity_name
        for entity_name in ordered_candidate_names
        if not any(
            role_by_url.get(str(source_url)) == SourceRole.VERIFICATION
            for source_url in extractor_light_output.name_to_source_urls.get(entity_name, [])
        )
    ]

    verification_gaps: list[EntityVerificationGap] = []
    for start_index in range(0, len(missing_verification_entities), MAX_ENTITIES_PER_VERIFICATION_QUERY):
        grouped_entities = missing_verification_entities[
            start_index : start_index + MAX_ENTITIES_PER_VERIFICATION_QUERY
        ]
        suggested_query = _verification_query(
            entity_names=grouped_entities,
            planner_output=planner_output,
        )
        for entity_name in grouped_entities:
            verification_gaps.append(
                EntityVerificationGap(
                    entity_name=entity_name,
                    mention_count=extractor_light_output.mention_counts.get(entity_name, 0),
                    suggested_query=suggested_query,
                )
            )
    return verification_gaps


def _select_jina_urls(
    *,
    assessed_sources: list[AssessedSource],
    evidence_store: EvidenceStore,
    remaining_fetch_budget: int,
) -> list[HttpUrl]:
    if remaining_fetch_budget <= 0:
        return []

    url_counts_by_role = _url_counts_by_role(evidence_store)
    scored_urls = sorted(
        (
            (
                _jina_priority_score(
                    assessed_source,
                    url_counts_by_role=url_counts_by_role,
                ),
                assessed_source,
            )
            for assessed_source in assessed_sources
            if assessed_source.should_deep_fetch
        ),
        key=lambda item: item[0],
        reverse=True,
    )

    selected_urls: list[HttpUrl] = []
    seen_urls: set[str] = set()
    for score, assessed_source in scored_urls:
        if score <= 0:
            continue
        url_key = str(assessed_source.result.url)
        if url_key in seen_urls:
            continue
        seen_urls.add(url_key)
        selected_urls.append(assessed_source.result.url)
        if len(selected_urls) >= remaining_fetch_budget:
            break
    return selected_urls


def _jina_priority_score(
    assessed_source: AssessedSource,
    *,
    url_counts_by_role: dict[str, int],
) -> float:
    role_bonus = 2.0 if assessed_source.source_role == SourceRole.VERIFICATION else 0.0
    only_verification_bonus = (
        2.0
        if assessed_source.source_role == SourceRole.VERIFICATION
        and url_counts_by_role.get(str(assessed_source.result.url), 0) == 1
        else 0.0
    )
    aspect_bonus = 0.6 * len(assessed_source.estimated_aspect_coverage)
    sufficiency_gap = 1.0 - assessed_source.evidence_sufficiency
    return (
        JINA_OFFICIALITY_SCORE[assessed_source.officiality]
        + JINA_QUALITY_SCORE[assessed_source.source_quality]
        + role_bonus
        + only_verification_bonus
        + aspect_bonus
        + sufficiency_gap
    )


def _url_counts_by_role(evidence_store: EvidenceStore) -> dict[str, int]:
    url_counts: dict[str, int] = {}
    for chunks in evidence_store.chunks_by_entity.values():
        for chunk in chunks:
            if chunk.source_role != SourceRole.VERIFICATION:
                continue
            url_key = str(chunk.source_url)
            url_counts[url_key] = url_counts.get(url_key, 0) + 1
    return url_counts


def _verification_query(*, entity_names: list[str], planner_output: PlannerOutput) -> str:
    entity_clause = " OR ".join(f'"{entity_name}"' for entity_name in entity_names if entity_name.strip())
    aspect_clause = " ".join(planner_output.core_aspects[:2])
    query = " ".join(
        value.strip()
        for value in [
            entity_clause,
            planner_output.entity_type,
            aspect_clause,
            "official",
        ]
        if value.strip()
    )
    return query[:400]


def _should_deep_fetch_source(
    *,
    source_role: SourceRole,
    source_quality: SourceQuality,
    officiality: OfficialityLevel,
    aspect_coverage: list[str],
    evidence_sufficiency: float,
) -> bool:
    if officiality in {OfficialityLevel.OFFICIAL, OfficialityLevel.NEAR_OFFICIAL}:
        return True
    if source_role == SourceRole.VERIFICATION and source_quality != SourceQuality.LOW:
        return True
    if aspect_coverage and evidence_sufficiency < 0.7:
        return True
    return evidence_sufficiency < 0.45 and source_quality == SourceQuality.HIGH


def _fetch_reason(
    *,
    source_role: SourceRole,
    source_quality: SourceQuality,
    officiality: OfficialityLevel,
    evidence_sufficiency: float,
) -> str:
    if officiality in {OfficialityLevel.OFFICIAL, OfficialityLevel.NEAR_OFFICIAL}:
        return "official or near-official source"
    if source_role == SourceRole.VERIFICATION:
        return "verification source with high retrieval value"
    if evidence_sufficiency < 0.45:
        return "Brave context is too thin for reliable extraction"
    return f"{source_quality.value} quality source covering requested aspects"


def _fallback_source_role(heuristic_signals: HeuristicSourceSignals) -> SourceRole:
    if heuristic_signals.official_path_hint >= 1.0 or heuristic_signals.domain_match_hint >= 0.75:
        return SourceRole.VERIFICATION
    if heuristic_signals.relevance_hint >= 0.25:
        return SourceRole.CORROBORATION
    return SourceRole.DISCOVERY


def _fallback_source_quality(heuristic_signals: HeuristicSourceSignals) -> SourceQuality:
    if heuristic_signals.snippet_thinness_hint >= 0.8 or heuristic_signals.relevance_hint < 0.1:
        return SourceQuality.LOW
    if heuristic_signals.rank_hint <= 3 or heuristic_signals.relevance_hint >= 0.3:
        return SourceQuality.HIGH
    return SourceQuality.MEDIUM


def _fallback_officiality(heuristic_signals: HeuristicSourceSignals) -> OfficialityLevel:
    if heuristic_signals.official_path_hint >= 1.0 and heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.OFFICIAL
    if heuristic_signals.domain_match_hint >= 0.5:
        return OfficialityLevel.NEAR_OFFICIAL
    if heuristic_signals.source_metadata.get("hostname") in {"linkedin.com", "crunchbase.com"}:
        return OfficialityLevel.THIRD_PARTY
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


def _has_official_path(url: HttpUrl) -> bool:
    path = urlparse(str(url)).path.lower()
    return any(marker in path for marker in OFFICIAL_PATH_MARKERS)


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if len(token) > 1
    }


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, numerator / denominator))
