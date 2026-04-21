from __future__ import annotations

import json

from backend.app.api_clients import StructuredLlmClient
from backend.app.contracts import ExtractorOutput
from backend.app.helpers import (
    ColumnAwareChunkRankingOutput,
    DefaultEntityGapFiller,
    GapFillColumnDecision,
    GapFillEntityOutput,
    GapFillMerger,
    RankedColumnChunk,
)
from backend.app.helpers.entity_gap_filler import _build_gap_filler_payload
from backend.tests.fixtures.factories import (
    make_extracted_entity,
    make_field_value,
    make_planner_output,
    make_retrieved_chunk,
    make_url_source,
)


class FakeStructuredGapFillClient(StructuredLlmClient):
    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[GapFillEntityOutput],
        reasoning_effort: str | None = None,
    ) -> GapFillEntityOutput:
        _ = model
        _ = system_prompt
        _ = user_content
        _ = response_model
        _ = reasoning_effort
        return GapFillEntityOutput(
            entity_name="PathAI",
            fields=[
                GapFillColumnDecision(
                    column_name="funding",
                    value="Raised a Series B round",
                    confidence=0.82,
                    supporting_chunk_ids=["jina:https://example.com/pathai#0"],
                )
            ],
        )


def test_gap_filler_payload_includes_only_missing_fields_and_new_chunks() -> None:
    payload = json.loads(
        _build_gap_filler_payload(
            planner_output=make_planner_output(),
            entity=make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={
                    "funding": make_field_value(value=None, confidence=0.0),
                    "location": make_field_value(value="Boston", confidence=0.9),
                },
            ),
            missing_columns=["funding"],
            evidence_chunks_by_column={
                "funding": [
                    type("Chunk", (), {
                        "chunk_id": "jina:https://example.com/pathai#0",
                        "source_url": "https://example.com/pathai",
                        "source_title": "PathAI Funding",
                        "text": "PathAI raised a Series B round from investors.",
                    })()
                ]
            },
        )
    )

    assert payload["existing_fields"] == {"location": "Boston"}
    assert payload["missing_columns"] == ["funding"]
    assert payload["evidence_chunks"][0]["chunk_id"] == "jina:https://example.com/pathai#0"
    assert payload["evidence_chunks"][0]["column"] == "funding"


def test_default_entity_gap_filler_and_merger_fill_only_missing_fields() -> None:
    gap_filler = DefaultEntityGapFiller(llm_client=FakeStructuredGapFillClient())
    original_output = ExtractorOutput(
        entities=[
            make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={
                    "funding": make_field_value(value=None, confidence=0.0),
                    "location": make_field_value(value="Boston", confidence=0.9),
                },
            )
        ]
    )
    ranking_output = ColumnAwareChunkRankingOutput(
        url_sources=[
            make_url_source(
                source_id="jina:https://example.com/pathai",
                url="https://example.com/pathai",
                title="PathAI Funding",
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#0",
                        source_id="jina:https://example.com/pathai",
                        text="PathAI raised a Series B round from investors.",
                    )
                ],
            )
        ],
        ranked_chunks=[
            RankedColumnChunk(
                entity_name="PathAI",
                column="funding",
                chunk_id="jina:https://example.com/pathai#0",
                source_id="jina:https://example.com/pathai",
                score=0.91,
                rank=1,
            )
        ],
    )

    gap_fill_result = gap_filler.run(
        planner_output=make_planner_output(),
        extractor_output=original_output,
        ranking_output=ranking_output,
    )
    merged_output = GapFillMerger().merge(
        extractor_output=original_output,
        gap_fill_result=gap_fill_result,
    )

    assert gap_fill_result.fields_filled == 1
    assert merged_output.entities[0].fields["funding"].value == "Raised a Series B round"
    assert merged_output.entities[0].fields["location"].value == "Boston"
