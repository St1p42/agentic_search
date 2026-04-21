from __future__ import annotations

from backend.app.helpers import (
    ColumnFacet,
    ColumnFacetOutput,
    DefaultBreadthV2QueryBuilder,
)


def test_breadth_v2_query_builder_builds_one_query_per_facet_in_order() -> None:
    builder = DefaultBreadthV2QueryBuilder()

    bundle = builder.build(
        normalized_query="AI startups in healthcare",
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(
                    column="founders",
                    facet_terms=["founder", "cofounder", "leadership team"],
                ),
                ColumnFacet(
                    column="location",
                    facet_terms=["headquarters", "based in", "offices"],
                ),
            ]
        ),
        max_queries=3,
    )

    assert [(item.column, item.query) for item in bundle.column_queries] == [
        (
            "founders",
            "AI startups in healthcare founder cofounder leadership team",
        ),
        (
            "location",
            "AI startups in healthcare headquarters based in offices",
        ),
    ]


def test_breadth_v2_query_builder_respects_query_cap() -> None:
    builder = DefaultBreadthV2QueryBuilder()

    bundle = builder.build(
        normalized_query="AI startups in healthcare",
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(column="founders", facet_terms=["founder"]),
                ColumnFacet(column="location", facet_terms=["headquarters"]),
            ]
        ),
        max_queries=1,
    )

    assert [(item.column, item.query) for item in bundle.column_queries] == [
        ("founders", "AI startups in healthcare founder")
    ]
