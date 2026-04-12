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
