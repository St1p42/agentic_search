from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.app.contracts import ExtractorOutput


DEFAULT_MIN_SPARSE_FILL_RATE = 0.60


@dataclass(frozen=True)
class SparseColumnSummary:
    sparse_columns: list[str]
    fill_rate_by_column: dict[str, float]


class SparseColumnDetector(Protocol):
    def detect(
        self,
        *,
        schema_columns: list[str],
        extractor_output: ExtractorOutput | None,
    ) -> SparseColumnSummary:
        """Return sparse schema columns and fill rates from first-pass extraction."""


class DefaultSparseColumnDetector:
    def __init__(self, *, min_sparse_fill_rate: float = DEFAULT_MIN_SPARSE_FILL_RATE) -> None:
        self._min_sparse_fill_rate = max(0.0, min(1.0, min_sparse_fill_rate))

    def detect(
        self,
        *,
        schema_columns: list[str],
        extractor_output: ExtractorOutput | None,
    ) -> SparseColumnSummary:
        if not schema_columns:
            return SparseColumnSummary(sparse_columns=[], fill_rate_by_column={})

        entities = extractor_output.entities if extractor_output is not None else []
        if not entities:
            fill_rate_by_column = {column: 0.0 for column in schema_columns}
            return SparseColumnSummary(
                sparse_columns=list(schema_columns),
                fill_rate_by_column=fill_rate_by_column,
            )

        entity_count = len(entities)
        fill_rate_by_column: dict[str, float] = {}
        sparse_columns: list[str] = []
        for column in schema_columns:
            non_null_count = sum(
                1
                for entity in entities
                if entity.fields.get(column) is not None
                and entity.fields[column].value is not None
            )
            fill_rate = non_null_count / entity_count
            fill_rate_by_column[column] = fill_rate
            if fill_rate < self._min_sparse_fill_rate:
                sparse_columns.append(column)

        return SparseColumnSummary(
            sparse_columns=sparse_columns,
            fill_rate_by_column=fill_rate_by_column,
        )
