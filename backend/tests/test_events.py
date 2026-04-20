from __future__ import annotations

from backend.app.contracts import RankingCandidatesStageUiModel


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
