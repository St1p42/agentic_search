from __future__ import annotations

from typing import Protocol

from backend.app.contracts import CanonicalEntity


class FinalRowRule(Protocol):
    def should_prune(self, row: CanonicalEntity) -> bool:
        """Return True when the row should be removed from final output."""


class MissingNameRule:
    def should_prune(self, row: CanonicalEntity) -> bool:
        name_field = row.fields.get("name")
        return name_field is None or name_field.value is None


class AllFieldsEmptyRule:
    def should_prune(self, row: CanonicalEntity) -> bool:
        return all(field.value is None for field in row.fields.values())


class NoGroundedNonNameFieldRule:
    def should_prune(self, row: CanonicalEntity) -> bool:
        non_name_fields = [
            field
            for field_name, field in row.fields.items()
            if field_name != "name"
        ]
        return not any(field.value is not None for field in non_name_fields)


class FinalRowPruner:
    def __init__(self, rules: list[FinalRowRule] | None = None) -> None:
        self._rules = rules or [
            MissingNameRule(),
            AllFieldsEmptyRule(),
            NoGroundedNonNameFieldRule(),
        ]

    def prune(self, rows: list[CanonicalEntity]) -> list[CanonicalEntity]:
        return [
            row
            for row in rows
            if not any(rule.should_prune(row) for rule in self._rules)
        ]
