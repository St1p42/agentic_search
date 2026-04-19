from __future__ import annotations

from backend.app.helpers.chunk_retrieval_preprocessor import DefaultChunkRetrievalPreprocessor


def test_preprocessor_normalizes_tokenizes_filters_and_stems() -> None:
    preprocessor = DefaultChunkRetrievalPreprocessor()

    tokens = preprocessor.preprocess_text("Clinician-facing AI systems, for hospitals and care teams!")

    assert "clinician" in tokens
    assert "facing" in tokens
    assert "ai" in tokens
    assert "system" in tokens
    assert "hospital" in tokens
    assert "and" not in tokens
