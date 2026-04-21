from __future__ import annotations

from backend.app.contracts import EvidenceItem, ExtractorOutput, FieldValue
from backend.app.helpers.sparse_column_detector import DefaultSparseColumnDetector
from backend.tests.fixtures.factories import make_extracted_entity


def _field_value(value: str | None) -> FieldValue:
    if value is None:
        return FieldValue(value=None, confidence=0.0, evidence=[])
    return FieldValue(
        value=value,
        confidence=1.0,
        evidence=[
            EvidenceItem(
                source_url="https://example.com",
                source_title="Example",
                supporting_snippet=value,
            )
        ],
    )


def test_sparse_column_detector_marks_columns_below_fill_rate_threshold() -> None:
    detector = DefaultSparseColumnDetector(min_sparse_fill_rate=0.6)

    summary = detector.detect(
        schema_columns=["category", "location", "website"],
        extractor_output=ExtractorOutput(
            entities=[
                make_extracted_entity(
                    candidate_id="Acme Health",
                    entity_name="Acme Health",
                    provisional=False,
                    fields={
                        "category": _field_value("Clinical AI"),
                        "location": _field_value("Boston"),
                        "website": _field_value(None),
                    },
                ),
                make_extracted_entity(
                    candidate_id="PathAI",
                    entity_name="PathAI",
                    provisional=False,
                    fields={
                        "category": _field_value("Digital pathology"),
                        "location": _field_value(None),
                        "website": _field_value(None),
                    },
                ),
            ]
        ),
    )

    assert summary.sparse_columns == ["location", "website"]
    assert summary.fill_rate_by_column == {
        "category": 1.0,
        "location": 0.5,
        "website": 0.0,
    }


def test_sparse_column_detector_treats_missing_extractor_output_as_all_sparse() -> None:
    detector = DefaultSparseColumnDetector(min_sparse_fill_rate=0.6)

    summary = detector.detect(
        schema_columns=["category", "location"],
        extractor_output=None,
    )

    assert summary.sparse_columns == ["category", "location"]
    assert summary.fill_rate_by_column == {"category": 0.0, "location": 0.0}
