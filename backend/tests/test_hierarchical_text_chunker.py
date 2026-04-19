from __future__ import annotations

from backend.app.helpers.hierarchical_text_chunker import HierarchicalTextChunker


def test_chunker_splits_hierarchically_and_preserves_order() -> None:
    text = (
        "# Overview\n"
        "Alpha Labs builds clinical AI tools for hospitals.\n\n"
        "# Product\n"
        "The platform supports workflow automation across intake, scheduling, and chart review. "
        "It integrates with hospital systems and clinician-facing dashboards.\n\n"
        "# Team\n"
        "Founded in Boston."
    )

    chunks = HierarchicalTextChunker(target_chunk_chars=120, max_chunks=10).chunk(
        text=text,
        source_id="jina:https://example.com/alpha",
    )

    assert len(chunks) >= 3
    assert chunks[0].text.startswith("# Overview")
    assert "# Product" in "".join(chunk.text for chunk in chunks)
    assert "".join(chunk.text for chunk in chunks).replace("\n", "").replace(" ", "").startswith(
        text.replace("\n", "").replace(" ", "")[:40]
    )


def test_chunker_merges_short_leaf_with_shorter_immediate_neighbor() -> None:
    text = (
        "A" * 65
        + "\n\n"
        + "tiny"
        + "\n\n"
        + "B" * 20
        + "\n\n"
        + "C" * 90
    )

    chunks = HierarchicalTextChunker(
        target_chunk_chars=70,
        min_chunk_chars=25,
        max_chunks=10,
    ).chunk(
        text=text,
        source_id="jina:https://example.com/merge",
    )

    assert len(chunks) == 3
    assert "tiny" in chunks[1].text
    assert "B" * 20 in chunks[1].text
    assert "C" * 90 in chunks[2].text


def test_chunker_respects_max_chunk_cap_by_merging_adjacent_chunks() -> None:
    text = "\n\n".join(f"Section {index} " + ("x" * 35) for index in range(1, 6))

    chunks = HierarchicalTextChunker(target_chunk_chars=50, max_chunks=3).chunk(
        text=text,
        source_id="jina:https://example.com/capped",
    )

    assert len(chunks) == 3
    assert chunks[0].sequence_index == 0
    assert chunks[-1].sequence_index == 2
