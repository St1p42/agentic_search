from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.app.helpers.column_facet_generator import ColumnFacetOutput


@dataclass(frozen=True)
class ColumnQuery:
    column: str
    query: str


@dataclass(frozen=True)
class BreadthV2QueryBundle:
    column_queries: list[ColumnQuery]


class BreadthV2QueryBuilder(Protocol):
    def build(
        self,
        *,
        normalized_query: str,
        facet_output: ColumnFacetOutput,
        max_queries: int,
    ) -> BreadthV2QueryBundle:
        """Build one breadth-v2 query per sparse column."""


class DefaultBreadthV2QueryBuilder:
    def build(
        self,
        *,
        normalized_query: str,
        facet_output: ColumnFacetOutput,
        max_queries: int,
    ) -> BreadthV2QueryBundle:
        normalized_base = " ".join(normalized_query.split()).strip()
        if not normalized_base or max_queries <= 0:
            return BreadthV2QueryBundle(column_queries=[])

        column_queries: list[ColumnQuery] = []
        for facet in facet_output.facets[:max_queries]:
            facet_terms = " ".join(
                term.strip()
                for term in facet.facet_terms
                if term.strip()
            ).strip()
            if not facet_terms:
                continue
            column_queries.append(
                ColumnQuery(
                    column=facet.column,
                    query=f"{normalized_base} {facet_terms}".strip(),
                )
            )

        return BreadthV2QueryBundle(column_queries=column_queries)
