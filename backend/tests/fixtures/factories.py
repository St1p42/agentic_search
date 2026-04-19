from __future__ import annotations

from pydantic import HttpUrl

from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    BraveContextPassage,
    EvidenceChunk,
    EvidenceItem,
    EvidenceOrigin,
    EvidenceStore,
    ExtractedEntity,
    ExtractorLightOutput,
    ExtractorOutput,
    FieldValue,
    HeuristicSourceSignals,
    OfficialityLevel,
    PlannerOutput,
    RetrievedChunk,
    SearchResultItem,
    SearcherOutput,
    SourceQuality,
    SourceRole,
    UrlSource,
)


def make_planner_output(
    *,
    entity_type: str = "startup",
    query_mode: str = "topic_entity_discovery",
    schema_columns: list[str] | None = None,
    core_aspects: list[str] | None = None,
    base_query: str = "AI startups in healthcare",
    initial_query_rewrites: list[str] | None = None,
    is_topic_query: bool = True,
    normalized_query: str | None = None,
    error: bool = False,
    error_message: str | None = None,
) -> PlannerOutput:
    return PlannerOutput(
        entity_type=entity_type,
        query_mode=query_mode,
        schema_columns=schema_columns or ["name", "website", "location", "focus_area"],
        core_aspects=core_aspects or ["focus_area", "location"],
        base_query=base_query,
        initial_query_rewrites=initial_query_rewrites or [],
        is_topic_query=is_topic_query,
        normalized_query=normalized_query or base_query,
        error=error,
        error_message=error_message,
    )


def make_search_result(
    *,
    url: str = "https://acmehealth.com/about",
    title: str = "About Acme Health",
    snippet: str = "Acme Health builds clinical AI systems.",
    domain: str = "acmehealth.com",
    rank: int = 1,
    query_sources: list[str] | None = None,
    result_type: str = "search_result",
    provider_metadata: dict[str, str] | None = None,
) -> SearchResultItem:
    return SearchResultItem(
        url=HttpUrl(url),
        title=title,
        snippet=snippet,
        domain=domain,
        rank=rank,
        query_sources=query_sources or ["AI startups in healthcare"],
        result_type=result_type,
        provider_metadata=provider_metadata or {"source": "brave_web_search"},
    )


def make_searcher_output(
    *,
    executed_queries: list[str] | None = None,
    raw_results: list[SearchResultItem] | None = None,
    shortlisted_results: list[SearchResultItem] | None = None,
) -> SearcherOutput:
    results = raw_results or []
    return SearcherOutput(
        executed_queries=executed_queries or ["AI startups in healthcare"],
        raw_results=results,
        shortlisted_results=shortlisted_results or list(results),
    )


def make_brave_context_passage(
    *,
    source_url: str = "https://acmehealth.com/about",
    passage_text: str = "Acme Health develops clinical AI systems for hospitals and care teams.",
    metadata: dict[str, str | bool] | None = None,
) -> BraveContextPassage:
    return BraveContextPassage(
        source_url=HttpUrl(source_url),
        passage_text=passage_text,
        metadata=metadata or {"title": "About Acme Health"},
    )


def make_brave_context_output(
    *,
    passages_by_url: dict[HttpUrl, list[BraveContextPassage]] | None = None,
) -> BraveContextOutput:
    return BraveContextOutput(passages_by_url=passages_by_url or {})


def make_extractor_light_output(
    *,
    candidate_names: list[str] | None = None,
    name_to_source_urls: dict[str, list[HttpUrl]] | None = None,
    mention_counts: dict[str, int] | None = None,
) -> ExtractorLightOutput:
    return ExtractorLightOutput(
        candidate_names=candidate_names or ["Acme Health"],
        name_to_source_urls=name_to_source_urls
        or {"Acme Health": [HttpUrl("https://acmehealth.com/about")]},
        mention_counts=mention_counts or {"Acme Health": 1},
    )


def make_heuristic_signals(
    *,
    relevance_hint: float = 1.0,
    domain_match_hint: float = 1.0,
    official_path_hint: float = 1.0,
    snippet_thinness_hint: float = 0.0,
    rank_hint: int = 1,
    source_metadata: dict[str, str] | None = None,
) -> HeuristicSourceSignals:
    return HeuristicSourceSignals(
        relevance_hint=relevance_hint,
        domain_match_hint=domain_match_hint,
        official_path_hint=official_path_hint,
        snippet_thinness_hint=snippet_thinness_hint,
        rank_hint=rank_hint,
        source_metadata=source_metadata or {"hostname": "acmehealth.com"},
    )


def make_assessed_source(
    *,
    result: SearchResultItem | None = None,
    brave_context_passages: list[BraveContextPassage] | None = None,
    heuristic_signals: HeuristicSourceSignals | None = None,
    source_role: SourceRole = SourceRole.VERIFICATION,
    source_quality: SourceQuality = SourceQuality.HIGH,
    officiality: OfficialityLevel = OfficialityLevel.OFFICIAL,
    estimated_aspect_coverage: list[str] | None = None,
    evidence_sufficiency: float = 0.95,
    should_deep_fetch: bool = False,
    fetch_reason: str | None = None,
    filtered_out: bool = False,
) -> AssessedSource:
    search_result = result or make_search_result()
    passages = brave_context_passages or [
        make_brave_context_passage(source_url=str(search_result.url))
    ]
    return AssessedSource(
        result=search_result,
        brave_context_passages=passages,
        heuristic_signals=heuristic_signals
        or make_heuristic_signals(source_metadata={"hostname": search_result.domain}),
        source_role=source_role,
        source_quality=source_quality,
        officiality=officiality,
        estimated_aspect_coverage=estimated_aspect_coverage or ["focus_area"],
        evidence_sufficiency=evidence_sufficiency,
        should_deep_fetch=should_deep_fetch,
        fetch_reason=fetch_reason,
        filtered_out=filtered_out,
    )


def make_assessor_output(
    *,
    pass_type: AssessorPass = AssessorPass.FIRST_PASS,
    assessed_sources: list[AssessedSource] | None = None,
    verification_gaps: list[str] | None = None,
    selected_jina_urls: list[HttpUrl] | None = None,
) -> AssessorOutput:
    return AssessorOutput(
        pass_type=pass_type,
        assessed_sources=assessed_sources or [],
        verification_gaps=verification_gaps or [],
        selected_jina_urls=selected_jina_urls or [],
    )


def make_retrieved_chunk(
    *,
    chunk_id: str = "jina:https://acmehealth.com/about#0",
    source_id: str = "jina:https://acmehealth.com/about",
    text: str = "Acme Health develops clinical AI systems for hospitals and care teams.",
    sequence_index: int = 0,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        source_id=source_id,
        text=text,
        sequence_index=sequence_index,
    )


def make_url_source(
    *,
    source_id: str = "jina:https://acmehealth.com/about",
    url: str = "https://acmehealth.com/about",
    title: str = "About Acme Health",
    origin: EvidenceOrigin = EvidenceOrigin.JINA,
    metadata: dict[str, str | int | float | bool | None] | None = None,
    chunks: list[RetrievedChunk] | None = None,
) -> UrlSource:
    return UrlSource(
        source_id=source_id,
        url=HttpUrl(url),
        title=title,
        origin=origin,
        metadata=metadata or {},
        chunks=chunks or [make_retrieved_chunk(source_id=source_id)],
    )


def make_evidence_chunk(
    *,
    text: str = "Acme Health develops clinical AI systems for hospitals and care teams.",
    source_url: str = "https://acmehealth.com/about",
    source_title: str = "About Acme Health",
    source_role: SourceRole = SourceRole.VERIFICATION,
    source_quality: SourceQuality = SourceQuality.HIGH,
    officiality: OfficialityLevel = OfficialityLevel.OFFICIAL,
    origin: EvidenceOrigin = EvidenceOrigin.BRAVE_LLM,
    aspect_coverage: list[str] | None = None,
) -> EvidenceChunk:
    return EvidenceChunk(
        text=text,
        source_url=HttpUrl(source_url),
        source_title=source_title,
        source_role=source_role,
        source_quality=source_quality,
        officiality=officiality,
        origin=origin,
        aspect_coverage=aspect_coverage or ["focus_area"],
    )


def make_evidence_store(
    *,
    chunks_by_entity: dict[str, list[EvidenceChunk]] | None = None,
    entity_scores: dict[str, float] | None = None,
) -> EvidenceStore:
    return EvidenceStore(
        chunks_by_entity=chunks_by_entity or {"Acme Health": [make_evidence_chunk()]},
        entity_scores=entity_scores or {},
    )


def make_evidence_item(
    *,
    source_url: str = "https://acmehealth.com/about",
    source_title: str = "About Acme Health",
    supporting_snippet: str = "Acme Health develops clinical AI systems for hospitals and care teams.",
    source_role: SourceRole = SourceRole.VERIFICATION,
    source_quality: SourceQuality = SourceQuality.HIGH,
    officiality: OfficialityLevel = OfficialityLevel.OFFICIAL,
) -> EvidenceItem:
    return EvidenceItem(
        source_url=HttpUrl(source_url),
        source_title=source_title,
        supporting_snippet=supporting_snippet,
        source_role=source_role,
        source_quality=source_quality,
        officiality=officiality,
    )


def make_field_value(
    *,
    value: str | None = "Acme Health",
    confidence: float = 1.0,
    evidence: list[EvidenceItem] | None = None,
) -> FieldValue:
    if value is None:
        return FieldValue(value=None, confidence=confidence, evidence=[])
    return FieldValue(
        value=value,
        confidence=confidence,
        evidence=evidence or [make_evidence_item()],
    )


def make_extracted_entity(
    *,
    candidate_id: str = "Acme Health",
    entity_name: str = "Acme Health",
    fields: dict[str, FieldValue] | None = None,
    source_urls: list[HttpUrl] | None = None,
    provisional: bool = False,
) -> ExtractedEntity:
    return ExtractedEntity(
        candidate_id=candidate_id,
        entity_name=entity_name,
        fields=fields
        or {
            "name": make_field_value(),
            "website": make_field_value(value=None, confidence=0.0),
            "location": make_field_value(value=None, confidence=0.0),
            "focus_area": make_field_value(
                value="clinical AI systems for hospitals and care teams.",
                confidence=0.84,
            ),
        },
        source_urls=source_urls or [HttpUrl("https://acmehealth.com/about")],
        provisional=provisional,
    )


def make_extractor_output(
    *,
    entities: list[ExtractedEntity] | None = None,
) -> ExtractorOutput:
    return ExtractorOutput(entities=entities or [make_extracted_entity()])
