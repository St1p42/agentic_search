from __future__ import annotations

import json

from backend.app.api_clients import StructuredLlmClient
from backend.app.helpers.source_bucket_classifier import (
    DefaultSourceBucketClassifier,
    SourceBucketDecision,
    SourceBucketModelOutput,
    _build_payload,
)
from backend.tests.fixtures.factories import make_planner_output, make_search_result


class FakeStructuredBucketClient(StructuredLlmClient):
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[SourceBucketModelOutput],
        reasoning_effort: str | None = None,
    ) -> SourceBucketModelOutput:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "reasoning_effort": reasoning_effort or "",
            }
        )
        _ = response_model
        return SourceBucketModelOutput(
            decisions=[
                SourceBucketDecision(
                    url="https://example.com/list",
                    bucket="roundup_list",
                    confidence=0.9,
                    reason="Title and snippet indicate a multi-entity list page.",
                )
            ]
        )


def test_source_bucket_classifier_builds_expected_payload() -> None:
    payload = json.loads(
        _build_payload(
            planner_output=make_planner_output(
                base_query="best entertainment places and things to do in Bucharest",
                normalized_query="entertainment places and things to do in Bucharest",
                initial_query_rewrites=["Bucharest nightlife venues"],
            ),
            search_results=[
                make_search_result(
                    url="https://example.com/list",
                    title="Best things to do in Bucharest",
                    snippet="A roundup of attractions and activities in Bucharest.",
                    query_sources=["best entertainment places and things to do in Bucharest"],
                )
            ],
        )
    )

    assert payload["normalized_query"] == "entertainment places and things to do in Bucharest"
    assert payload["base_query"] == "best entertainment places and things to do in Bucharest"
    assert payload["query_rewrites"] == ["Bucharest nightlife venues"]
    assert payload["sources"][0]["url"] == "https://example.com/list"


def test_source_bucket_classifier_returns_decisions_keyed_by_url() -> None:
    fake_client = FakeStructuredBucketClient()
    classifier = DefaultSourceBucketClassifier(llm_client=fake_client)

    decisions = classifier.classify(
        planner_output=make_planner_output(),
        search_results=[
            make_search_result(
                url="https://example.com/list",
                title="Best healthcare AI startups",
                snippet="A roundup of notable companies.",
            )
        ],
    )

    assert list(decisions) == ["https://example.com/list"]
    assert decisions["https://example.com/list"].bucket == "roundup_list"
    assert fake_client.calls[0]["model"] == "gpt-5-mini"
