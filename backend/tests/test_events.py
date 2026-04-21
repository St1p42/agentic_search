from __future__ import annotations

from backend.app.contracts import (
    ClassifyingSourcesStageUiModel,
    EnrichingExtractedEntitiesStageUiModel,
    RankingCandidatesStageUiModel,
)


def test_ranking_candidates_stage_ui_model_exposes_expected_metrics() -> None:
    details = RankingCandidatesStageUiModel(
        core_candidates_kept=8,
        discovery_candidates_kept=2,
        core_candidates_filtered=3,
        discovery_candidates_filtered=5,
    ).to_ui_details()

    assert details.summary == "Filtered and ranked candidates before profile building"
    assert [(metric.label, metric.value) for metric in details.metrics] == [
        ("Core candidates kept", 8),
        ("Discovery candidates kept", 2),
        ("Core candidates filtered", 3),
        ("Discovery candidates filtered", 5),
    ]


def test_classifying_sources_stage_ui_model_exposes_expected_metrics() -> None:
    details = ClassifyingSourcesStageUiModel(
        official_sources=1,
        profile_sources=2,
        roundup_sources=4,
        editorial_reference_sources=3,
        transactional_sources=1,
    ).to_ui_details()

    assert details.summary == "Grouped shortlisted sources by source type"
    assert [(metric.label, metric.value) for metric in details.metrics] == [
        ("Official sources", 1),
        ("Profile sources", 2),
        ("Roundup sources", 4),
        ("Editorial/reference sources", 3),
        ("Transactional sources", 1),
    ]


def test_enriching_extracted_entities_stage_ui_model_exposes_expected_metrics() -> None:
    details = EnrichingExtractedEntitiesStageUiModel(
        sparse_columns_targeted=2,
        enrichment_queries_run=2,
        extra_sources_fetched=6,
        passages_shortlisted=9,
        fields_filled=4,
    ).to_ui_details()

    assert details.summary == "Searched for stronger evidence to fill missing fields"
    assert [(metric.label, metric.value) for metric in details.metrics] == [
        ("Sparse columns targeted", 2),
        ("Enrichment queries run", 2),
        ("Extra sources fetched", 6),
        ("Passages shortlisted", 9),
        ("Fields filled", 4),
    ]
