from __future__ import annotations

import json

from backend.app.helpers.source_bucket_classifier import SourceBucketDecision
from backend.app.helpers.source_bucket_dataset_writer import JsonlSourceBucketDatasetWriter
from backend.tests.fixtures.factories import make_planner_output, make_search_result


def test_source_bucket_dataset_writer_appends_deduped_rows(tmp_path) -> None:
    dataset_path = tmp_path / "source_bucket_dataset.jsonl"
    writer = JsonlSourceBucketDatasetWriter(dataset_path=dataset_path)
    planner_output = make_planner_output(
        base_query="best entertainment places and things to do in Bucharest",
        normalized_query="entertainment places and things to do in Bucharest",
        initial_query_rewrites=["Bucharest nightlife venues"],
    )
    search_result = make_search_result(
        url="https://example.com/list",
        title="Best things to do in Bucharest",
        snippet="A roundup of attractions and activities in Bucharest.",
        query_sources=["best entertainment places and things to do in Bucharest"],
    )
    decisions_by_url = {
        "https://example.com/list": SourceBucketDecision(
            url="https://example.com/list",
            bucket="roundup_list",
            confidence=0.9,
            reason="List-style page.",
        )
    }

    writer.write(
        planner_output=planner_output,
        search_results=[search_result],
        decisions_by_url=decisions_by_url,
    )
    writer.write(
        planner_output=planner_output,
        search_results=[search_result],
        decisions_by_url=decisions_by_url,
    )

    rows = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["bucket"] == "roundup_list"
    assert rows[0]["judge_model"] == "gpt-5-mini"
