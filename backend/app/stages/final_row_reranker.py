from __future__ import annotations

from backend.app.contracts import CanonicalEntity


class FinalRowReranker:
    def rerank(self, rows: list[CanonicalEntity]) -> list[CanonicalEntity]:
        indexed_rows = list(enumerate(rows))
        reranked = sorted(
            indexed_rows,
            key=lambda item: (
                -_grounded_non_name_field_count(item[1]),
                -_grounded_field_count(item[1]),
                -_distinct_source_url_count(item[1]),
                item[0],
            ),
        )
        return [row for _, row in reranked]


def _grounded_non_name_field_count(row: CanonicalEntity) -> int:
    return sum(
        1
        for field_name, field in row.fields.items()
        if field_name != "name" and field.value is not None
    )


def _grounded_field_count(row: CanonicalEntity) -> int:
    return sum(1 for field in row.fields.values() if field.value is not None)


def _distinct_source_url_count(row: CanonicalEntity) -> int:
    return len({str(url) for url in row.source_urls})
