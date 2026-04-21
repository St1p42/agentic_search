from __future__ import annotations

from pydantic import HttpUrl

from backend.app.contracts import (
    AssessedSource,
    EvidenceOrigin,
    OfficialityLevel,
    RetrievedChunk,
    SearchResultItem,
    SourceQuality,
    SourceRole,
)
from backend.app.helpers.evidence_store_builder import DefaultEvidenceStoreBuilder
from backend.tests.fixtures.factories import (
    make_assessed_source,
    make_assessor_output,
    make_chunk_ranking_output,
    make_evidence_chunk,
    make_evidence_store,
    make_extractor_light_output,
    make_heuristic_signals,
    make_retrieved_chunk,
    make_search_result,
    make_url_source,
)


def _assessed_source(result: SearchResultItem, chunk: RetrievedChunk) -> AssessedSource:
    return make_assessed_source(
        result=result,
        retrieved_chunks=[chunk],
        heuristic_signals=make_heuristic_signals(
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

    mapped_result = make_search_result(
        url=str(mapped_url),
        title="Mapped Source",
        snippet="Mapped snippet",
        domain="example.com",
        query_sources=["best phones 2026"],
    )
    fallback_result = make_search_result(
        url=str(fallback_url),
        title="Fallback Source",
        snippet="Fallback snippet",
        domain="example.com",
        query_sources=["best phones 2026"],
    )

    mapped_chunk = make_retrieved_chunk(
        chunk_id="jina:https://example.com/mapped#0",
        source_id="jina:https://example.com/mapped",
        text="Acme Phone is a strong all-rounder. It has excellent battery life.",
    )
    fallback_chunk = make_retrieved_chunk(
        chunk_id="jina:https://example.com/fallback#0",
        source_id="jina:https://example.com/fallback",
        text="Other phones exist. Acme Phone has great battery life for creators. It charges quickly.",
    )

    output = builder.run(
        chunk_ranking_output=make_chunk_ranking_output(
            url_sources=[
                make_url_source(
                    source_id="jina:https://example.com/mapped",
                    url=str(mapped_url),
                    chunks=[mapped_chunk],
                ),
                make_url_source(
                    source_id="jina:https://example.com/fallback",
                    url=str(fallback_url),
                    metadata={"fallback": True},
                    chunks=[fallback_chunk],
                ),
            ],
            ranked_chunks=[],
            selected_chunk_ids=[mapped_chunk.chunk_id, fallback_chunk.chunk_id],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Phone"],
            name_to_source_urls={"Acme Phone": [mapped_url]},
            mention_counts={"Acme Phone": 2},
        ),
        assessor_output=make_assessor_output(
            assessed_sources=[
                _assessed_source(mapped_result, mapped_chunk),
                _assessed_source(fallback_result, fallback_chunk),
            ],
        ),
    )

    chunks = output.chunks_by_entity["Acme Phone"]
    assert len(chunks) == 2
    assert {chunk.source_url for chunk in chunks} == {mapped_url, fallback_url}
    assert all(chunk.origin == EvidenceOrigin.JINA for chunk in chunks)
    assert output.entity_scores["Acme Phone"] == 2.0
    assert all(chunk.query_sources == ["best phones 2026"] for chunk in chunks)
    assert any(chunk.text == "Acme Phone is a strong all-rounder. It has excellent battery life." for chunk in chunks)
    assert any(
        chunk.text == "Other phones exist. Acme Phone has great battery life for creators. It charges quickly."
        for chunk in chunks
    )


def test_evidence_store_builder_attaches_selected_chunk_rank() -> None:
    builder = DefaultEvidenceStoreBuilder()
    source_url = HttpUrl("https://example.com/ranked")
    result = make_search_result(
        url=str(source_url),
        title="Ranked Source",
        snippet="Ranked snippet",
        domain="example.com",
        query_sources=["best phones 2026", "camera phones 2026"],
    )
    chunk = make_retrieved_chunk(
        chunk_id="jina:https://example.com/ranked#0",
        source_id="jina:https://example.com/ranked",
        text="Acme Phone is a strong all-rounder for creators and photographers.",
    )

    output = builder.run(
        chunk_ranking_output=make_chunk_ranking_output(
            url_sources=[
                make_url_source(
                    source_id="jina:https://example.com/ranked",
                    url=str(source_url),
                    chunks=[chunk],
                )
            ],
            ranked_chunks=[
                {
                    "source_id": "jina:https://example.com/ranked",
                    "chunk_id": chunk.chunk_id,
                    "rank": 3,
                    "score": {"final_score": 0.9},
                }
            ],
            selected_chunk_ids=[chunk.chunk_id],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Phone"],
            name_to_source_urls={"Acme Phone": [source_url]},
            mention_counts={"Acme Phone": 2},
        ),
        assessor_output=make_assessor_output(
            assessed_sources=[_assessed_source(result, chunk)],
        ),
    )

    evidence_chunk = output.chunks_by_entity["Acme Phone"][0]
    assert evidence_chunk.selected_chunk_rank == 3
    assert evidence_chunk.query_sources == ["best phones 2026", "camera phones 2026"]


def test_evidence_store_builder_keeps_ambiguous_matches_and_dedupes_existing_chunks() -> None:
    builder = DefaultEvidenceStoreBuilder()
    shared_url = HttpUrl("https://example.com/shared")
    shared_result = make_search_result(
        url=str(shared_url),
        title="Shared Source",
        snippet="Shared snippet",
        domain="example.com",
        query_sources=["best phones 2026"],
    )
    shared_chunk = make_retrieved_chunk(
        chunk_id="jina:https://example.com/shared#0",
        source_id="jina:https://example.com/shared",
        text=(
            "Alpha Phone is built for creators and has a polished camera system. "
            "Beta Phone is built for gamers and delivers top-tier sustained performance."
        ),
    )
    shared_assessed_source = _assessed_source(shared_result, shared_chunk)
    existing_chunk = make_evidence_chunk(
        text="Alpha Phone is built for creators and has a polished camera system.",
        source_url=str(shared_url),
        source_title="Shared Source",
        source_role=SourceRole.CORROBORATION,
        source_quality=SourceQuality.HIGH,
        officiality=OfficialityLevel.THIRD_PARTY,
        origin=EvidenceOrigin.BRAVE_LLM,
        aspect_coverage=["target_use_case"],
    )

    output = builder.run(
        chunk_ranking_output=make_chunk_ranking_output(
            url_sources=[
                make_url_source(
                    source_id="jina:https://example.com/shared",
                    url=str(shared_url),
                    chunks=[shared_chunk],
                )
            ],
            selected_chunk_ids=[shared_chunk.chunk_id],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Alpha Phone", "Beta Phone"],
            name_to_source_urls={},
            mention_counts={"Alpha Phone": 2, "Beta Phone": 2},
        ),
        assessor_output=make_assessor_output(
            assessed_sources=[shared_assessed_source],
        ),
        existing_store=make_evidence_store(chunks_by_entity={"Alpha Phone": [existing_chunk]}),
    )

    assert len(output.chunks_by_entity["Alpha Phone"]) == 1
    assert len(output.chunks_by_entity["Beta Phone"]) == 1
    assert output.chunks_by_entity["Beta Phone"][0].text == (
        "Beta Phone is built for gamers and delivers top-tier sustained performance."
    )


def test_evidence_store_builder_does_not_stop_on_weak_one_off_entity_mentions() -> None:
    builder = DefaultEvidenceStoreBuilder()
    source_url = HttpUrl("https://example.com/window")
    chunk = make_retrieved_chunk(
        chunk_id="jina:https://example.com/window#0",
        source_id="jina:https://example.com/window",
        text=(
            "Acme Phone is the best pick for creators. "
            "It has outstanding battery life. "
            "Weak Model gets a brief mention. "
            "Its software is also polished."
        ),
    )
    result = make_search_result(
        url=str(source_url),
        title="Window Source",
        snippet="Window snippet",
        domain="example.com",
        query_sources=["best phones 2026"],
    )

    output = builder.run(
        chunk_ranking_output=make_chunk_ranking_output(
            url_sources=[
                make_url_source(
                    source_id="jina:https://example.com/window",
                    url=str(source_url),
                    chunks=[chunk],
                )
            ],
            selected_chunk_ids=[chunk.chunk_id],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Acme Phone", "Weak Model"],
            name_to_source_urls={"Acme Phone": [source_url]},
            mention_counts={"Acme Phone": 2, "Weak Model": 1},
        ),
        assessor_output=make_assessor_output(
            assessed_sources=[_assessed_source(result, chunk)],
        ),
    )

    assert output.chunks_by_entity["Acme Phone"][0].text == (
        "Acme Phone is the best pick for creators. "
        "It has outstanding battery life. "
        "Weak Model gets a brief mention. "
        "Its software is also polished."
    )
