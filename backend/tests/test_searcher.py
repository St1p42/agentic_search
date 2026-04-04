from __future__ import annotations

from fastapi.testclient import TestClient

from backend.app.api_clients import BraveSearchClient, BraveWebResult
from backend.app.config import SearcherRuntimeConfig
from backend.app.contracts import PlannerOutput, SearcherOutput
from backend.app.main import app
from backend.app.stages import PlaceholderSearcherStage
from backend.app.stages.searcher import BraveSearcherStage


class FakeBraveSearchClient(BraveSearchClient):
    def __init__(self, results_by_query: dict[str, list[BraveWebResult]]) -> None:
        self._results_by_query = results_by_query
        self.calls: list[tuple[str, int]] = []

    def search_web(self, *, query: str, count: int) -> list[BraveWebResult]:
        self.calls.append((query, count))
        return list(self._results_by_query.get(query, []))[:count]


def _planner_output(
    *,
    base_query: str = "AI startups in healthcare",
    rewrites: list[str] | None = None,
) -> PlannerOutput:
    return PlannerOutput(
        entity_type="startup",
        query_mode="topic_entity_discovery",
        schema_columns=["name", "clinical_application", "technology_type", "website"],
        core_aspects=["clinical_application", "technology_type"],
        base_query=base_query,
        initial_query_rewrites=rewrites or [],
        is_topic_query=True,
        normalized_query=base_query,
    )


def _searcher_config(*, weak_pool_threshold: int = 0) -> SearcherRuntimeConfig:
    return SearcherRuntimeConfig(
        mode="brave",
        brave_search_api_key="fake-key",
        weak_pool_threshold=weak_pool_threshold,
    )


def _brave_result(
    *,
    url: str,
    title: str,
    snippet: str,
    domain: str,
    rank: int,
) -> BraveWebResult:
    return BraveWebResult(
        url=url,
        title=title,
        snippet=snippet,
        domain=domain,
        rank=rank,
        result_type="search_result",
        provider_metadata={"source": "brave_web_search"},
    )


def test_brave_searcher_executes_queries_with_dynamic_count_map() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://example.com/a",
                    title="Clinical AI startup",
                    snippet="Healthcare AI for diagnostics",
                    domain="example.com",
                    rank=1,
                )
            ],
            "healthcare AI startups": [
                _brave_result(
                    url="https://example.com/b",
                    title="Healthcare AI platform",
                    snippet="AI startup for hospital operations",
                    domain="example.com",
                    rank=1,
                )
            ],
            "medical AI startups": [
                _brave_result(
                    url="https://example.com/c",
                    title="Medical AI company",
                    snippet="AI product for clinical workflows",
                    domain="example.com",
                    rank=1,
                )
            ],
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=_searcher_config(weak_pool_threshold=0),
        brave_client=fake_client,
    )

    output = searcher.run(
        _planner_output(
            rewrites=["healthcare AI startups", "medical AI startups"],
        )
    )

    assert output.executed_queries == [
        "AI startups in healthcare",
        "healthcare AI startups",
        "medical AI startups",
    ]
    assert fake_client.calls == [
        ("AI startups in healthcare", 12),
        ("healthcare AI startups", 12),
        ("medical AI startups", 12),
    ]
    assert [str(result.url) for result in output.shortlisted_results] == [
        "https://example.com/a",
        "https://example.com/b",
        "https://example.com/c",
    ]


def test_brave_searcher_prunes_dedupes_and_merges_best_rank() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://example.com/shared",
                    title="Clinical AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="example.com",
                    rank=3,
                ),
                _brave_result(
                    url="https://twitter.com/acme/status/123",
                    title="Tweet",
                    snippet="Healthcare AI startup launch",
                    domain="twitter.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://example.com/file.pdf",
                    title="PDF",
                    snippet="Healthcare AI report",
                    domain="example.com",
                    rank=2,
                ),
                _brave_result(
                    url="https://youtube.com/watch?v=1",
                    title="Video",
                    snippet="Healthcare AI startup",
                    domain="youtube.com",
                    rank=4,
                ),
                _brave_result(
                    url="https://example.com/empty",
                    title="Empty",
                    snippet="",
                    domain="example.com",
                    rank=5,
                ),
                _brave_result(
                    url="https://example.com/boilerplate",
                    title="Login",
                    snippet="Sign in to continue",
                    domain="example.com",
                    rank=6,
                ),
                _brave_result(
                    url="https://example.com/no-overlap",
                    title="Gardening tips",
                    snippet="Grow tomatoes and herbs",
                    domain="example.com",
                    rank=7,
                ),
                _brave_result(
                    url="https://linkedin.com/company/acme",
                    title="Acme Health",
                    snippet="Healthcare AI company",
                    domain="linkedin.com",
                    rank=8,
                ),
            ],
            "medical AI startups": [
                _brave_result(
                    url="https://example.com/shared",
                    title="Better Clinical AI startup",
                    snippet="Medical AI startup diagnostics",
                    domain="example.com",
                    rank=1,
                ),
            ],
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=_searcher_config(weak_pool_threshold=0),
        brave_client=fake_client,
    )

    output = searcher.run(_planner_output(rewrites=["medical AI startups"]))

    assert [str(result.url) for result in output.shortlisted_results] == [
        "https://example.com/shared",
        "https://linkedin.com/company/acme",
    ]
    shared = output.shortlisted_results[0]
    assert shared.rank == 1
    assert shared.title == "Better Clinical AI startup"
    assert shared.query_sources == ["AI startups in healthcare", "medical AI startups"]


def test_brave_searcher_retries_once_on_weak_pool_with_retry_count_map() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://example.com/a",
                    title="Clinical AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="example.com",
                    rank=1,
                )
            ]
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=_searcher_config(weak_pool_threshold=8),
        brave_client=fake_client,
    )

    output = searcher.run(_planner_output(), max_search_queries=2)

    assert output.executed_queries == [
        "AI startups in healthcare",
        "AI startups in healthcare",
    ]
    assert fake_client.calls == [
        ("AI startups in healthcare", 20),
        ("AI startups in healthcare", 32),
    ]
    assert [str(result.url) for result in output.shortlisted_results] == ["https://example.com/a"]


def test_brave_searcher_honors_max_search_queries_and_skips_retry_without_budget() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://example.com/a",
                    title="Clinical AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="example.com",
                    rank=1,
                )
            ],
            "healthcare AI startups": [
                _brave_result(
                    url="https://example.com/b",
                    title="Healthcare AI company",
                    snippet="Medical AI startup",
                    domain="example.com",
                    rank=1,
                )
            ],
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=_searcher_config(weak_pool_threshold=8),
        brave_client=fake_client,
    )

    output = searcher.run(
        _planner_output(rewrites=["healthcare AI startups", "medical AI startups"]),
        max_search_queries=2,
    )

    assert output.executed_queries == [
        "AI startups in healthcare",
        "healthcare AI startups",
    ]
    assert fake_client.calls == [
        ("AI startups in healthcare", 15),
        ("healthcare AI startups", 15),
    ]


def test_brave_searcher_uses_query_source_tiebreaker_and_domain_cap() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://alpha.com/a",
                    title="Alpha AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="alpha.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://beta.com/a",
                    title="Beta AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="beta.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://same.com/1",
                    title="Same One AI",
                    snippet="Healthcare AI clinical application",
                    domain="same.com",
                    rank=2,
                ),
                _brave_result(
                    url="https://same.com/2",
                    title="Same Two AI",
                    snippet="Healthcare AI clinical application",
                    domain="same.com",
                    rank=2,
                ),
                _brave_result(
                    url="https://same.com/3",
                    title="Same Three AI",
                    snippet="Healthcare AI clinical application",
                    domain="same.com",
                    rank=2,
                ),
                _brave_result(
                    url="https://same.com/4",
                    title="Same Four AI",
                    snippet="Healthcare AI clinical application",
                    domain="same.com",
                    rank=2,
                ),
            ],
            "medical AI startups": [
                _brave_result(
                    url="https://alpha.com/a",
                    title="Alpha AI startup",
                    snippet="Healthcare AI diagnostics",
                    domain="alpha.com",
                    rank=1,
                ),
            ],
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=_searcher_config(weak_pool_threshold=0),
        brave_client=fake_client,
    )

    output = searcher.run(_planner_output(rewrites=["medical AI startups"]))

    assert [str(result.url) for result in output.shortlisted_results] == [
        "https://alpha.com/a",
        "https://beta.com/a",
        "https://same.com/1",
        "https://same.com/2",
        "https://same.com/3",
    ]
    assert output.shortlisted_results[0].query_sources == [
        "AI startups in healthcare",
        "medical AI startups",
    ]


def test_brave_searcher_round_robin_reserved_slots_preserve_rewrite_coverage() -> None:
    fake_client = FakeBraveSearchClient(
        {
            "AI startups in healthcare": [
                _brave_result(
                    url="https://example.com/shared-1",
                    title="Shared One AI startup",
                    snippet="Healthcare AI clinical application",
                    domain="example.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://example.com/shared-2",
                    title="Shared Two AI startup",
                    snippet="Healthcare AI technology type",
                    domain="example.com",
                    rank=2,
                ),
                _brave_result(
                    url="https://base.com/only",
                    title="Base Only AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="base.com",
                    rank=3,
                ),
                _brave_result(
                    url="https://base.com/2",
                    title="Base Two AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="base.com",
                    rank=4,
                ),
                _brave_result(
                    url="https://base.com/3",
                    title="Base Three AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="base.com",
                    rank=5,
                ),
                _brave_result(
                    url="https://extra.com/1",
                    title="Extra One AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="extra.com",
                    rank=6,
                ),
                _brave_result(
                    url="https://extra.com/2",
                    title="Extra Two AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="extra.com",
                    rank=7,
                ),
                _brave_result(
                    url="https://extra.com/3",
                    title="Extra Three AI startup",
                    snippet="Healthcare AI clinical platform",
                    domain="extra.com",
                    rank=8,
                ),
            ],
            "medical AI startups": [
                _brave_result(
                    url="https://example.com/shared-1",
                    title="Shared One AI startup",
                    snippet="Healthcare AI clinical application",
                    domain="example.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://rewrite.com/only",
                    title="Rewrite Only Medical AI",
                    snippet="Medical AI clinical application",
                    domain="rewrite.com",
                    rank=9,
                ),
            ],
        }
    )
    searcher = BraveSearcherStage(
        runtime_config=SearcherRuntimeConfig(
            mode="brave",
            brave_search_api_key="fake-key",
            shortlist_cap=8,
            weak_pool_threshold=0,
        ),
        brave_client=fake_client,
    )

    output = searcher.run(_planner_output(rewrites=["medical AI startups"]))

    assert str(output.shortlisted_results[1].url) == "https://rewrite.com/only"


def test_searcher_test_endpoint_accepts_planner_output(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.main.build_searcher_stage",
        lambda runtime_config: PlaceholderSearcherStage(),
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/searcher/test",
        json=_planner_output(rewrites=["healthcare AI startups"]).model_dump(mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body == SearcherOutput(
        executed_queries=["AI startups in healthcare", "healthcare AI startups"],
        raw_results=[],
        shortlisted_results=[],
    ).model_dump(mode="json")
