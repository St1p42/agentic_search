from __future__ import annotations

from backend.app.helpers import (
    ColumnFacet,
    ColumnFacetOutput,
    DefaultColumnAwareChunkRanker,
)
from backend.tests.fixtures.factories import (
    make_extracted_entity,
    make_field_value,
    make_retrieved_chunk,
    make_url_source,
)


def test_column_aware_chunk_ranker_prefers_focused_column_relevant_chunks() -> None:
    ranker = DefaultColumnAwareChunkRanker()

    output = ranker.run(
        normalized_query="AI startups in healthcare",
        extracted_entities=[
            make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={"funding": make_field_value(value=None, confidence=0.0)},
            ),
            make_extracted_entity(
                candidate_id="Abridge",
                entity_name="Abridge",
                fields={"funding": make_field_value(value=None, confidence=0.0)},
            ),
        ],
        sparse_columns=["funding"],
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(
                    column="funding",
                    facet_terms=["funding", "raised", "investors", "series b"],
                )
            ]
        ),
        url_sources=[
            make_url_source(
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#0",
                        source_id="jina:https://example.com/pathai",
                        text="PathAI raised a Series B round from investors to expand its healthcare AI platform.",
                    ),
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/list#0",
                        source_id="jina:https://example.com/list",
                        text="PathAI and Abridge are healthcare AI startups mentioned in a roundup of companies to watch.",
                    ),
                ]
            )
        ],
    )

    ranked_chunks = output.top_chunks_for(entity_name="PathAI", column="funding")

    assert [chunk.chunk_id for chunk in ranked_chunks] == [
        "jina:https://example.com/pathai#0",
        "jina:https://example.com/list#0",
    ]
    assert ranked_chunks[0].score > ranked_chunks[1].score


def test_column_aware_chunk_ranker_discards_chunks_without_target_entity_mentions() -> None:
    ranker = DefaultColumnAwareChunkRanker()

    output = ranker.run(
        normalized_query="AI startups in healthcare",
        extracted_entities=[
            make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={"funding": make_field_value(value=None, confidence=0.0)},
            )
        ],
        sparse_columns=["funding"],
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(
                    column="funding",
                    facet_terms=["funding", "raised", "investors"],
                )
            ]
        ),
        url_sources=[
            make_url_source(
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/generic#0",
                        source_id="jina:https://example.com/generic",
                        text="Healthcare AI startups raised funding from investors across the sector.",
                    )
                ]
            )
        ],
    )

    assert output.top_chunks_for(entity_name="PathAI", column="funding") == []


def test_column_aware_chunk_ranker_keeps_at_most_one_chunk_per_source_for_entity_column() -> None:
    ranker = DefaultColumnAwareChunkRanker()

    output = ranker.run(
        normalized_query="AI startups in healthcare",
        extracted_entities=[
            make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={"funding": make_field_value(value=None, confidence=0.0)},
            )
        ],
        sparse_columns=["funding"],
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(
                    column="funding",
                    facet_terms=["funding", "raised", "investors", "series b"],
                )
            ]
        ),
        url_sources=[
            make_url_source(
                source_id="jina:https://example.com/pathai",
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#0",
                        source_id="jina:https://example.com/pathai",
                        text="PathAI raised a Series B round from investors to expand its healthcare AI platform.",
                    ),
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#1",
                        source_id="jina:https://example.com/pathai",
                        text="PathAI funding history includes investors and follow-on rounds in healthcare AI.",
                    ),
                ],
            ),
            make_url_source(
                source_id="jina:https://example.com/profile",
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/profile#0",
                        source_id="jina:https://example.com/profile",
                        text=(
                            "PathAI raised a Series B funding round from investors and expanded its healthcare AI "
                            "platform for pathology teams."
                        ),
                    )
                ],
            ),
        ],
    )

    ranked_chunks = output.top_chunks_for(entity_name="PathAI", column="funding")

    assert {chunk.source_id for chunk in ranked_chunks[:2]} == {
        "jina:https://example.com/pathai",
        "jina:https://example.com/profile",
    }


def test_column_aware_chunk_ranker_allows_same_source_reuse_when_materially_stronger() -> None:
    ranker = DefaultColumnAwareChunkRanker()

    output = ranker.run(
        normalized_query="AI startups in healthcare",
        extracted_entities=[
            make_extracted_entity(
                candidate_id="PathAI",
                entity_name="PathAI",
                fields={"funding": make_field_value(value=None, confidence=0.0)},
            )
        ],
        sparse_columns=["funding"],
        facet_output=ColumnFacetOutput(
            facets=[
                ColumnFacet(
                    column="funding",
                    facet_terms=["funding", "raised", "investors", "series b"],
                )
            ]
        ),
        url_sources=[
            make_url_source(
                source_id="jina:https://example.com/pathai",
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#0",
                        source_id="jina:https://example.com/pathai",
                        text="PathAI raised a Series B round from investors to expand its healthcare AI platform.",
                    ),
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/pathai#1",
                        source_id="jina:https://example.com/pathai",
                        text=(
                            "PathAI funding update: PathAI raised funding from investors in a large Series B "
                            "round for its healthcare AI platform."
                        ),
                    ),
                ],
            ),
            make_url_source(
                source_id="jina:https://example.com/profile",
                chunks=[
                    make_retrieved_chunk(
                        chunk_id="jina:https://example.com/profile#0",
                        source_id="jina:https://example.com/profile",
                        text="PathAI works in healthcare AI and machine learning for pathology teams.",
                    )
                ],
            ),
        ],
    )

    ranked_chunks = output.top_chunks_for(entity_name="PathAI", column="funding")

    assert len(ranked_chunks) == 3
    assert [chunk.source_id for chunk in ranked_chunks[:2]] == [
        "jina:https://example.com/pathai",
        "jina:https://example.com/pathai",
    ]
