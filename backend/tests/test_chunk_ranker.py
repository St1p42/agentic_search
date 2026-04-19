from __future__ import annotations

from backend.app.helpers.chunk_ranker import DefaultChunkRanker
from backend.tests.fixtures.factories import (
    make_planner_output,
    make_retrieved_chunk,
    make_url_source,
)


def test_chunk_ranker_prefers_best_rewrite_plus_support_bonus() -> None:
    planner_output = make_planner_output(
        base_query="AI startups in healthcare",
        normalized_query="AI startups in healthcare",
        initial_query_rewrites=["clinical AI startups", "hospital workflow automation startups"],
        core_aspects=["clinical ai", "workflow automation"],
    )
    url_sources = [
        make_url_source(
            source_id="jina:https://alpha.example/about",
            url="https://alpha.example/about",
            title="Alpha Health",
            chunks=[
                make_retrieved_chunk(
                    chunk_id="jina:https://alpha.example/about#0",
                    source_id="jina:https://alpha.example/about",
                    text=(
                        "Alpha Health is an AI startup in healthcare. "
                        "It builds clinical AI software for hospital workflow automation."
                    ),
                )
            ],
        ),
        make_url_source(
            source_id="jina:https://beta.example/about",
            url="https://beta.example/about",
            title="Beta Cameras",
            chunks=[
                make_retrieved_chunk(
                    chunk_id="jina:https://beta.example/about#0",
                    source_id="jina:https://beta.example/about",
                    text="Beta Cameras makes compact camera accessories for travel photographers.",
                )
            ],
        ),
    ]

    output = DefaultChunkRanker().run(planner_output, url_sources)

    assert len(output.scored_chunks) == 2
    assert output.scored_chunks[0].source_id == "jina:https://alpha.example/about"
    assert output.scored_chunks[0].best_rewrite_score > 0.0
    assert output.scored_chunks[0].query_variant_coverage_count >= 1
    assert output.scored_chunks[0].query_variant_coverage_score > 0.0
    assert output.scored_chunks[0].max_query_span_score > 0.0
    assert output.scored_chunks[0].anchor_coverage_score > 0.0
    assert output.scored_chunks[0].final_score > output.scored_chunks[1].final_score


def test_chunk_ranker_uses_core_bm25_formula_only() -> None:
    planner_output = make_planner_output(
        base_query="healthcare AI startups",
        normalized_query="healthcare AI startups",
        initial_query_rewrites=["clinical ai companies"],
        core_aspects=["clinical ai"],
    )
    url_sources = [
        make_url_source(
            source_id="jina:https://acmehealth.com/about",
            url="https://acmehealth.com/about",
            title="Healthcare startup overview",
            chunks=[
                make_retrieved_chunk(
                    chunk_id="jina:https://acmehealth.com/about#0",
                    source_id="jina:https://acmehealth.com/about",
                    text="Acme Health is a healthcare AI startup building clinical AI systems.",
                    sequence_index=0,
                ),
                make_retrieved_chunk(
                    chunk_id="jina:https://acmehealth.com/about#1",
                    source_id="jina:https://acmehealth.com/about",
                    text="Acme Health privacy policy and cookie policy for website visitors.",
                    sequence_index=1,
                ),
            ],
        ),
    ]

    output = DefaultChunkRanker().run(planner_output, url_sources)

    assert len(output.scored_chunks) == 2
    assert all(chunk.query_scores["base"] >= 0.0 for chunk in output.scored_chunks)
    assert all(chunk.query_variant_coverage_score >= 0.0 for chunk in output.scored_chunks)
    assert all(chunk.max_query_span_score >= 0.0 for chunk in output.scored_chunks)
    assert output.scored_chunks[0].aspect_overlap_score == 0.0
    assert output.scored_chunks[0].title_overlap_score == 0.0
    assert output.scored_chunks[0].official_domain_boost == 0.0
    assert output.scored_chunks[0].boilerplate_penalty == 0.0
