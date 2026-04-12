from __future__ import annotations

from backend.app.stages import ThinFinalizerStage
from backend.tests.fixtures.factories import (
    make_extracted_entity,
    make_extractor_output,
    make_field_value,
    make_planner_output,
)


def test_thin_finalizer_prunes_row_with_missing_name() -> None:
    finalizer = ThinFinalizerStage()

    output = finalizer.run(
        planner_output=make_planner_output(),
        extractor_output=make_extractor_output(
            entities=[
                make_extracted_entity(
                    fields={
                        "name": make_field_value(value=None, confidence=0.0),
                        "website": make_field_value(value="https://acmehealth.com", confidence=0.9),
                        "location": make_field_value(value=None, confidence=0.0),
                        "focus_area": make_field_value(value=None, confidence=0.0),
                    }
                )
            ]
        ),
    )

    assert output.final_rows == []


def test_thin_finalizer_prunes_fully_empty_row() -> None:
    finalizer = ThinFinalizerStage()

    output = finalizer.run(
        planner_output=make_planner_output(),
        extractor_output=make_extractor_output(
            entities=[
                make_extracted_entity(
                    fields={
                        "name": make_field_value(value=None, confidence=0.0),
                        "website": make_field_value(value=None, confidence=0.0),
                        "location": make_field_value(value=None, confidence=0.0),
                        "focus_area": make_field_value(value=None, confidence=0.0),
                    }
                )
            ]
        ),
    )

    assert output.final_rows == []


def test_thin_finalizer_prunes_name_only_row() -> None:
    finalizer = ThinFinalizerStage()

    output = finalizer.run(
        planner_output=make_planner_output(),
        extractor_output=make_extractor_output(
            entities=[
                make_extracted_entity(
                    fields={
                        "name": make_field_value(value="Acme Health", confidence=1.0),
                        "website": make_field_value(value=None, confidence=0.0),
                        "location": make_field_value(value=None, confidence=0.0),
                        "focus_area": make_field_value(value=None, confidence=0.0),
                    }
                )
            ]
        ),
    )

    assert output.final_rows == []


def test_thin_finalizer_keeps_row_with_grounded_non_name_field() -> None:
    finalizer = ThinFinalizerStage()

    output = finalizer.run(
        planner_output=make_planner_output(),
        extractor_output=make_extractor_output(
            entities=[
                make_extracted_entity(
                    fields={
                        "name": make_field_value(value="Acme Health", confidence=1.0),
                        "website": make_field_value(value=None, confidence=0.0),
                        "location": make_field_value(value=None, confidence=0.0),
                        "focus_area": make_field_value(value="clinical AI systems", confidence=0.84),
                    }
                )
            ]
        ),
    )

    assert len(output.final_rows) == 1
    assert output.final_rows[0].name == "Acme Health"


def test_thin_finalizer_reranks_richer_rows_above_sparse_rows() -> None:
    finalizer = ThinFinalizerStage()

    output = finalizer.run(
        planner_output=make_planner_output(),
        extractor_output=make_extractor_output(
            entities=[
                make_extracted_entity(
                    entity_name="Sparse Row",
                    candidate_id="Sparse Row",
                    source_urls=[],
                    fields={
                        "name": make_field_value(value="Sparse Row", confidence=1.0),
                        "website": make_field_value(value=None, confidence=0.0),
                        "location": make_field_value(value=None, confidence=0.0),
                        "focus_area": make_field_value(value="Mapping", confidence=0.84),
                    }
                ),
                make_extracted_entity(
                    entity_name="Richer Row",
                    candidate_id="Richer Row",
                    source_urls=[],
                    fields={
                        "name": make_field_value(value="Richer Row", confidence=1.0),
                        "website": make_field_value(value="https://aira.example.com", confidence=0.9),
                        "location": make_field_value(value="Sweden", confidence=0.88),
                        "focus_area": make_field_value(value="Residential heating", confidence=0.91),
                    }
                ),
            ]
        ),
    )

    assert [row.name for row in output.final_rows] == ["Richer Row", "Sparse Row"]
