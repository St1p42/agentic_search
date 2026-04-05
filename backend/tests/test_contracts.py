from __future__ import annotations

import pytest
from pydantic import HttpUrl, ValidationError

from backend.app.contracts import (
    AssessedSource,
    EvidenceChunk,
    EvidenceItem,
    EvidenceOrigin,
    EvidenceStore,
    FieldValue,
    HeuristicSourceSignals,
    OfficialityLevel,
    SearchResultItem,
    SourceQuality,
    SourceRole,
)
from backend.app.fixtures.seed_data import (
    EXAMPLE_EVIDENCE_STORE,
    EXAMPLE_FINAL_RESPONSE,
    EXAMPLE_PLANNER_OUTPUT,
    EXAMPLE_SSE_LIFECYCLE,
    SEED_QUERY,
)


def test_seed_fixtures_match_contracts() -> None:
    assert SEED_QUERY.query == "AI startups in healthcare"
    assert EXAMPLE_PLANNER_OUTPUT.base_query == SEED_QUERY.query
    assert EXAMPLE_FINAL_RESPONSE.request_id == SEED_QUERY.request_id
    assert EXAMPLE_SSE_LIFECYCLE[0].payload.request_id == SEED_QUERY.request_id
    assert "Example Health AI" in EXAMPLE_EVIDENCE_STORE.chunks_by_entity


def test_field_value_requires_evidence_for_non_null_value() -> None:
    with pytest.raises(ValidationError):
        FieldValue(value="unsupported", confidence=0.8, evidence=[])


def test_field_value_allows_null_without_evidence() -> None:
    field = FieldValue(value=None, confidence=0.0, evidence=[])
    assert field.value is None


def test_evidence_item_contract() -> None:
    item = EvidenceItem(
        source_url=HttpUrl("https://example.com"),
        source_title="Example",
        supporting_snippet="Example evidence",
        source_role=SourceRole.VERIFICATION,
        source_quality=SourceQuality.HIGH,
        officiality=OfficialityLevel.OFFICIAL,
    )
    assert item.source_role == SourceRole.VERIFICATION


def test_assessed_source_separates_heuristics_from_assessor_judgments() -> None:
    assessed = AssessedSource(
        result=SearchResultItem(
            url=HttpUrl("https://example.com/about"),
            title="About Example",
            snippet="Example snippet",
            domain="example.com",
            rank=1,
            result_type="web",
            provider_metadata={"source": "brave_web_search"},
        ),
        heuristic_signals=HeuristicSourceSignals(
            relevance_hint=0.9,
            domain_match_hint=0.8,
            official_path_hint=0.9,
            snippet_thinness_hint=0.1,
            rank_hint=1,
            source_metadata={"hostname": "example.com"},
        ),
        source_role=SourceRole.VERIFICATION,
        source_quality=SourceQuality.HIGH,
        officiality=OfficialityLevel.OFFICIAL,
        estimated_aspect_coverage=["identity"],
        evidence_sufficiency=0.8,
        should_deep_fetch=True,
        fetch_reason="official page likely contains core fields",
    )
    assert assessed.heuristic_signals.rank_hint == 1
    assert assessed.source_quality == SourceQuality.HIGH


def test_evidence_store_contract_groups_chunks_by_entity() -> None:
    store = EvidenceStore(
        chunks_by_entity={
            "Example Health AI": [
                EvidenceChunk(
                    text="Example evidence text",
                    source_url=HttpUrl("https://example.com/about"),
                    source_title="About Example",
                    source_role=SourceRole.VERIFICATION,
                    source_quality=SourceQuality.HIGH,
                    officiality=OfficialityLevel.OFFICIAL,
                    origin=EvidenceOrigin.BRAVE_LLM,
                    aspect_coverage=["identity"],
                )
            ]
        }
    )
    assert store.chunks_by_entity["Example Health AI"][0].origin == EvidenceOrigin.BRAVE_LLM
