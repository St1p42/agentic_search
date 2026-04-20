from __future__ import annotations

from backend.app.helpers.entity_reranker import DefaultEntityReranker
from backend.tests.fixtures.factories import (
    make_evidence_chunk,
    make_evidence_store,
    make_extractor_light_output,
    make_planner_output,
)


def test_entity_reranker_dedupes_near_duplicate_same_source_evidence() -> None:
    reranker = DefaultEntityReranker()

    result = reranker.run(
        planner_output=make_planner_output(
            entity_type="venue",
            base_query="best entertainment places and things to do in Bucharest",
            normalized_query="entertainment venues and activities in Bucharest",
            initial_query_rewrites=[
                "entertainment venues in Bucharest by type",
                "family-friendly activities and attractions in Bucharest",
                "entertainment options across Bucharest neighborhoods",
            ],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Good To See You Beauty Salon"],
            name_to_source_urls={},
            mention_counts={"Good To See You Beauty Salon": 3},
        ),
        evidence_store=make_evidence_store(
            chunks_by_entity={
                "Good To See You Beauty Salon": [
                    make_evidence_chunk(
                        text=(
                            "Good To See You Beauty Salon offers eyelash lamination, gel manicures, "
                            "and semi-permanent polish at reasonable prices."
                        ),
                        source_url="https://wanderlog.com/place/details/15085426/good-to-see-you-beauty-salon",
                        source_quality="medium",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=3,
                    ),
                    make_evidence_chunk(
                        text=(
                            "Good To See You Beauty Salon offers gel manicures, eyelash lamination, "
                            "and semi-permanent polish at reasonable prices."
                        ),
                        source_url="https://wanderlog.com/place/details/15085426/good-to-see-you-beauty-salon",
                        source_quality="medium",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=4,
                    ),
                ]
            },
            entity_scores={},
        ),
    )

    assert len(result.ranked_entities) == 1
    assert result.ranked_entities[0].features.deduped_unique_chunk_count == 1
    assert result.ranked_entities[0].features.unique_source_count == 1


def test_entity_reranker_prefers_multi_source_multi_query_aligned_entities_and_filters_drift() -> None:
    reranker = DefaultEntityReranker()

    result = reranker.run(
        planner_output=make_planner_output(
            entity_type="venue",
            base_query="best entertainment places and things to do in Bucharest",
            normalized_query="entertainment venues and activities in Bucharest",
            initial_query_rewrites=[
                "entertainment venues in Bucharest by type",
                "family-friendly activities and attractions in Bucharest",
                "entertainment options across Bucharest neighborhoods",
            ],
        ),
        extractor_light_output=make_extractor_light_output(
            candidate_names=["Deschis Gastrobar", "Good To See You Beauty Salon"],
            name_to_source_urls={},
            mention_counts={"Deschis Gastrobar": 4, "Good To See You Beauty Salon": 3},
        ),
        evidence_store=make_evidence_store(
            chunks_by_entity={
                "Deschis Gastrobar": [
                    make_evidence_chunk(
                        text=(
                            "Deschis Gastrobar is a Bucharest gastrobar with a rooftop terrace, live music, "
                            "and events near Splaiul Unirii."
                        ),
                        source_url="https://www.deschis-gastrobar.ro/",
                        source_quality="high",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=1,
                    ),
                    make_evidence_chunk(
                        text=(
                            "Deschis Gastrobar appears on Bucharest nightlife guides as a rooftop venue with "
                            "live music and late-night entertainment."
                        ),
                        source_url="https://www.visitromania.net/en/bucharest/bucharest-nightlife/",
                        source_quality="medium",
                        query_sources=["entertainment options across Bucharest neighborhoods"],
                        selected_chunk_rank=2,
                    ),
                ],
                "Good To See You Beauty Salon": [
                    make_evidence_chunk(
                        text=(
                            "Good To See You Beauty Salon offers eyelash lamination, gel manicures, "
                            "and semi-permanent polish at reasonable prices."
                        ),
                        source_url="https://wanderlog.com/place/details/15085426/good-to-see-you-beauty-salon",
                        source_quality="medium",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=3,
                    ),
                    make_evidence_chunk(
                        text=(
                            "Good To See You Beauty Salon offers gel manicures, eyelash lamination, "
                            "and semi-permanent polish at reasonable prices."
                        ),
                        source_url="https://wanderlog.com/place/details/15085426/good-to-see-you-beauty-salon",
                        source_quality="medium",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=4,
                    ),
                    make_evidence_chunk(
                        text="## 19 Good To See You Beauty Salon",
                        source_url="https://wanderlog.com/place/details/15085426/good-to-see-you-beauty-salon",
                        source_quality="medium",
                        query_sources=["entertainment venues in Bucharest by type"],
                        selected_chunk_rank=5,
                    ),
                ],
            },
            entity_scores={},
        ),
    )

    assert result.ranked_entity_names[0] == "Deschis Gastrobar"
    assert "Good To See You Beauty Salon" not in result.ranked_entity_names
    assert result.ranked_entities[0].features.unique_source_count == 2
    assert result.ranked_entities[0].features.query_variant_coverage_count == 2
