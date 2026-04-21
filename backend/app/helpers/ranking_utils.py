from __future__ import annotations


def dense_normalized_scores(
    *,
    result_ids: list[int],
    result_scores: list[float],
    corpus_size: int,
) -> list[float]:
    dense_scores = [0.0] * corpus_size
    for doc_id, score in zip(result_ids, result_scores, strict=False):
        if 0 <= doc_id < corpus_size:
            dense_scores[doc_id] = score
    max_score = max(dense_scores, default=0.0)
    if max_score <= 0.0:
        return dense_scores
    return [max(0.0, score / max_score) for score in dense_scores]
