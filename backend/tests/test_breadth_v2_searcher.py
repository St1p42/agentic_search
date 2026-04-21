from __future__ import annotations

from backend.app.api_clients import BraveSearchClient, BraveWebResult
from backend.app.helpers import BreadthV2SearchConfig, BreadthV2Searcher
from backend.tests.fixtures.factories import make_planner_output


class FakeBraveSearchClient(BraveSearchClient):
    def __init__(self, results_by_query: dict[str, list[BraveWebResult]]) -> None:
        self._results_by_query = results_by_query
        self.calls: list[tuple[str, int]] = []

    def search_web(self, *, query: str, count: int) -> list[BraveWebResult]:
        self.calls.append((query, count))
        return self._results_by_query.get(query, [])[:count]


def _brave_result(
    *,
    url: str,
    title: str,
    snippet: str,
    domain: str,
    rank: int,
) -> BraveWebResult:
    return BraveWebResult(
        title=title,
        url=url,
        snippet=snippet,
        domain=domain,
        rank=rank,
        result_type="search_result",
        provider_metadata={},
    )


def test_breadth_v2_searcher_dedupes_across_column_queries_and_caps_shortlist() -> None:
    client = FakeBraveSearchClient(
        {
            "AI startups in healthcare founder cofounder": [
                _brave_result(
                    url="https://example.com/a",
                    title="A",
                    snippet="Healthcare AI founder profile",
                    domain="example.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://example.com/shared",
                    title="Shared",
                    snippet="Healthcare AI startup profile",
                    domain="example.com",
                    rank=2,
                ),
            ],
            "AI startups in healthcare headquarters based in": [
                _brave_result(
                    url="https://example.com/shared",
                    title="Shared",
                    snippet="Healthcare AI startup profile",
                    domain="example.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://example.com/b",
                    title="B",
                    snippet="Healthcare AI headquarters and office locations",
                    domain="example.com",
                    rank=2,
                ),
            ],
        }
    )
    searcher = BreadthV2Searcher(
        brave_client=client,
        search_config=BreadthV2SearchConfig(sources_per_query=5, shortlist_cap=15),
    )

    output = searcher.run(
        planner_output=make_planner_output(),
        queries=[
            "AI startups in healthcare founder cofounder",
            "AI startups in healthcare headquarters based in",
        ],
    )

    assert output.executed_queries == [
        "AI startups in healthcare founder cofounder",
        "AI startups in healthcare headquarters based in",
    ]
    assert [str(result.url) for result in output.shortlisted_results] == [
        "https://example.com/shared",
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_breadth_v2_searcher_reuses_existing_pruning_for_obvious_trash() -> None:
    client = FakeBraveSearchClient(
        {
            "AI startups in healthcare founder cofounder": [
                _brave_result(
                    url="https://example.com/a.pdf",
                    title="PDF",
                    snippet="Healthcare AI founder profile",
                    domain="example.com",
                    rank=1,
                ),
                _brave_result(
                    url="https://example.com/real",
                    title="Real",
                    snippet="Healthcare AI founder and leadership team",
                    domain="example.com",
                    rank=2,
                ),
            ]
        }
    )
    searcher = BreadthV2Searcher(
        brave_client=client,
        search_config=BreadthV2SearchConfig(sources_per_query=5, shortlist_cap=15),
    )

    output = searcher.run(
        planner_output=make_planner_output(),
        queries=["AI startups in healthcare founder cofounder"],
    )

    assert [str(result.url) for result in output.shortlisted_results] == [
        "https://example.com/real",
    ]
