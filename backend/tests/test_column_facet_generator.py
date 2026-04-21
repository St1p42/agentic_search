from __future__ import annotations

import json

from backend.app.api_clients import StructuredLlmClient
from backend.app.helpers.column_facet_generator import (
    ColumnFacet,
    ColumnFacetOutput,
    DefaultColumnFacetGenerator,
    PlaceholderColumnFacetGenerator,
    _build_payload,
)


class FakeStructuredFacetClient(StructuredLlmClient):
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[ColumnFacetOutput],
        reasoning_effort: str | None = None,
    ) -> ColumnFacetOutput:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "user_content": user_content,
                "reasoning_effort": reasoning_effort or "",
            }
        )
        _ = response_model
        return ColumnFacetOutput(
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
        )


def test_column_facet_generator_builds_expected_payload() -> None:
    payload = json.loads(
        _build_payload(
            normalized_query="AI startups in healthcare",
            base_query="AI startups in healthcare",
            sparse_columns=["founders", "location"],
        )
    )

    assert payload == {
        "normalized_query": "AI startups in healthcare",
        "base_query": "AI startups in healthcare",
        "sparse_columns": ["founders", "location"],
    }


def test_default_column_facet_generator_returns_facets_in_input_column_order() -> None:
    fake_client = FakeStructuredFacetClient()
    generator = DefaultColumnFacetGenerator(llm_client=fake_client)

    output = generator.generate(
        normalized_query="AI startups in healthcare",
        base_query="AI startups in healthcare",
        sparse_columns=["founders", "location"],
    )

    assert output.facets == [
        ColumnFacet(
            column="founders",
            facet_terms=["founder", "cofounder", "leadership team"],
        ),
        ColumnFacet(
            column="location",
            facet_terms=["headquarters", "based in", "offices"],
        ),
    ]
    assert fake_client.calls[0]["model"] == "gpt-5-mini"


def test_default_column_facet_generator_dedupes_and_caps_facet_terms() -> None:
    class NoisyFacetClient(StructuredLlmClient):
        def parse(
            self,
            *,
            model: str,
            system_prompt: str,
            user_content: str,
            response_model: type[ColumnFacetOutput],
            reasoning_effort: str | None = None,
        ) -> ColumnFacetOutput:
            _ = model
            _ = system_prompt
            _ = user_content
            _ = response_model
            _ = reasoning_effort
            return ColumnFacetOutput.model_construct(
                facets=[
                    ColumnFacet.model_construct(
                        column="founders",
                        facet_terms=[
                            "founder",
                            "Founder",
                            "cofounder",
                            "leadership team",
                            "founded",
                            "executive team",
                        ],
                    )
                ]
            )

    generator = DefaultColumnFacetGenerator(llm_client=NoisyFacetClient())

    output = generator.generate(
        normalized_query="AI startups in healthcare",
        base_query="AI startups in healthcare",
        sparse_columns=["founders"],
    )

    assert output.facets == [
        ColumnFacet(
            column="founders",
            facet_terms=["founder", "cofounder", "leadership team", "founded"],
        )
    ]


def test_placeholder_column_facet_generator_falls_back_to_column_text() -> None:
    generator = PlaceholderColumnFacetGenerator()

    output = generator.generate(
        normalized_query="AI startups in healthcare",
        base_query="AI startups in healthcare",
        sparse_columns=["price_range"],
    )

    assert output == ColumnFacetOutput(
        facets=[ColumnFacet(column="price_range", facet_terms=["price range"])]
    )
