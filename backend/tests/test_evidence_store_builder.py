from __future__ import annotations

from pydantic import HttpUrl

from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    AssessorPass,
    BraveContextOutput,
    BraveContextPassage,
    EvidenceChunk,
    EvidenceOrigin,
    EvidenceStore,
    ExtractorLightOutput,
    HeuristicSourceSignals,
    OfficialityLevel,
    SearchResultItem,
    SourceQuality,
    SourceRole,
)
from backend.app.helpers.evidence_store_builder import DefaultEvidenceStoreBuilder


def _search_result(url: str, title: str, snippet: str, domain: str) -> SearchResultItem:
    return SearchResultItem(
        url=HttpUrl(url),
        title=title,
        snippet=snippet,
        domain=domain,
        rank=1,
        query_sources=["best phones 2026"],
        result_type="search_result",
        provider_metadata={"source": "brave_web_search"},
    )


def _assessed_source(result: SearchResultItem, passage: BraveContextPassage) -> AssessedSource:
    return AssessedSource(
        result=result,
        brave_context_passages=[passage],
        heuristic_signals=HeuristicSourceSignals(
            relevance_hint=1.0,
            domain_match_hint=0.0,
            official_path_hint=0.0,
            snippet_thinness_hint=0.0,
            rank_hint=1,
            source_metadata={"hostname": result.domain},
        ),
        source_role=SourceRole.CORROBORATION,
        source_quality=SourceQuality.HIGH,
        officiality=OfficialityLevel.THIRD_PARTY,
        estimated_aspect_coverage=["target_use_case"],
        evidence_sufficiency=0.8,
        should_deep_fetch=False,
        fetch_reason=None,
    )


def test_evidence_store_builder_attaches_url_mapped_and_fallback_chunks() -> None:
    builder = DefaultEvidenceStoreBuilder()

    mapped_url = HttpUrl("https://example.com/mapped")
    fallback_url = HttpUrl("https://example.com/fallback")

    mapped_result = _search_result(
        str(mapped_url),
        "Mapped Source",
        "Mapped snippet",
        "example.com",
    )
    fallback_result = _search_result(
        str(fallback_url),
        "Fallback Source",
        "Fallback snippet",
        "example.com",
    )

    mapped_passage = BraveContextPassage(
        source_url=mapped_url,
        passage_text="Acme Phone is a strong all-rounder. It has excellent battery life.",
        metadata={"title": "Mapped Source"},
    )
    fallback_passage = BraveContextPassage(
        source_url=fallback_url,
        passage_text="Other phones exist. Acme Phone has great battery life for creators. It charges quickly.",
        metadata={"title": "Fallback Source"},
    )

    output = builder.run(
        brave_context_output=BraveContextOutput(
            passages_by_url={
                mapped_url: [mapped_passage],
                fallback_url: [fallback_passage],
            }
        ),
        extractor_light_output=ExtractorLightOutput(
            candidate_names=["Acme Phone"],
            name_to_source_urls={"Acme Phone": [mapped_url]},
            mention_counts={"Acme Phone": 2},
        ),
        assessor_output=AssessorOutput(
            pass_type=AssessorPass.FIRST_PASS,
            assessed_sources=[
                _assessed_source(mapped_result, mapped_passage),
                _assessed_source(fallback_result, fallback_passage),
            ],
            verification_gaps=[],
            selected_jina_urls=[],
        ),
    )

    chunks = output.chunks_by_entity["Acme Phone"]
    assert len(chunks) == 2
    assert {chunk.source_url for chunk in chunks} == {mapped_url, fallback_url}
    assert all(chunk.origin == EvidenceOrigin.BRAVE_LLM for chunk in chunks)
    assert output.entity_scores["Acme Phone"] == 2.0
    assert any(chunk.text == "Acme Phone is a strong all-rounder. It has excellent battery life." for chunk in chunks)
    assert any(
        chunk.text == "Other phones exist. Acme Phone has great battery life for creators. It charges quickly."
        for chunk in chunks
    )


def test_evidence_store_builder_keeps_ambiguous_matches_and_dedupes_existing_chunks() -> None:
    builder = DefaultEvidenceStoreBuilder()
    shared_url = HttpUrl("https://example.com/shared")
    shared_result = _search_result(
        str(shared_url),
        "Shared Source",
        "Shared snippet",
        "example.com",
    )
    shared_passage = BraveContextPassage(
        source_url=shared_url,
        passage_text=(
            "Alpha Phone is built for creators and has a polished camera system. "
            "Beta Phone is built for gamers and delivers top-tier sustained performance."
        ),
        metadata={"title": "Shared Source"},
    )
    shared_assessed_source = _assessed_source(shared_result, shared_passage)
    existing_chunk = EvidenceChunk(
        text="Alpha Phone is built for creators and has a polished camera system.",
        source_url=shared_url,
        source_title="Shared Source",
        source_role=SourceRole.CORROBORATION,
        source_quality=SourceQuality.HIGH,
        officiality=OfficialityLevel.THIRD_PARTY,
        origin=EvidenceOrigin.BRAVE_LLM,
        aspect_coverage=["target_use_case"],
    )

    output = builder.run(
        brave_context_output=BraveContextOutput(passages_by_url={shared_url: [shared_passage]}),
        extractor_light_output=ExtractorLightOutput(
            candidate_names=["Alpha Phone", "Beta Phone"],
            name_to_source_urls={},
            mention_counts={"Alpha Phone": 2, "Beta Phone": 2},
        ),
        assessor_output=AssessorOutput(
            pass_type=AssessorPass.FIRST_PASS,
            assessed_sources=[shared_assessed_source],
            verification_gaps=[],
            selected_jina_urls=[],
        ),
        existing_store=EvidenceStore(chunks_by_entity={"Alpha Phone": [existing_chunk]}),
    )

    assert len(output.chunks_by_entity["Alpha Phone"]) == 1
    assert len(output.chunks_by_entity["Beta Phone"]) == 1
    assert output.chunks_by_entity["Beta Phone"][0].text == (
        "Beta Phone is built for gamers and delivers top-tier sustained performance."
    )


def test_evidence_store_builder_does_not_stop_on_weak_one_off_entity_mentions() -> None:
    builder = DefaultEvidenceStoreBuilder()
    source_url = HttpUrl("https://example.com/window")
    passage = BraveContextPassage(
        source_url=source_url,
        passage_text=(
            "Acme Phone is the best pick for creators. "
            "It has outstanding battery life. "
            "Weak Model gets a brief mention. "
            "Its software is also polished."
        ),
        metadata={"title": "Window Source"},
    )
    result = _search_result(str(source_url), "Window Source", "Window snippet", "example.com")

    output = builder.run(
        brave_context_output=BraveContextOutput(passages_by_url={source_url: [passage]}),
        extractor_light_output=ExtractorLightOutput(
            candidate_names=["Acme Phone", "Weak Model"],
            name_to_source_urls={"Acme Phone": [source_url]},
            mention_counts={"Acme Phone": 2, "Weak Model": 1},
        ),
        assessor_output=AssessorOutput(
            pass_type=AssessorPass.FIRST_PASS,
            assessed_sources=[_assessed_source(result, passage)],
            verification_gaps=[],
            selected_jina_urls=[],
        ),
    )

    assert output.chunks_by_entity["Acme Phone"][0].text == (
        "Acme Phone is the best pick for creators. "
        "It has outstanding battery life. "
        "Weak Model gets a brief mention. "
        "Its software is also polished."
    )
