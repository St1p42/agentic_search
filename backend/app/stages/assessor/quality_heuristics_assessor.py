from __future__ import annotations

from backend.app.contracts import HeuristicSourceSignals, SearchResultItem, SourceQuality, UrlSource
from backend.app.stages.assessor.models import QualityHeuristicAssessment
from backend.app.stages.assessor.utils import has_low_quality_host_marker, path, path_segment_count


THIN_SNIPPET_CHAR_THRESHOLD = 80
THIN_CONTEXT_CHAR_THRESHOLD = 80
VERY_THIN_FALLBACK_CONTEXT_CHAR_THRESHOLD = 140
LONG_PATH_CHAR_THRESHOLD = 90
LONG_PATH_SEGMENT_THRESHOLD = 6


class QualityHeuristicsAssessor:
    def assess(
        self,
        *,
        result: SearchResultItem,
        url_source: UrlSource | None,
        heuristic_signals: HeuristicSourceSignals,
    ) -> QualityHeuristicAssessment:
        score = 0
        reasons: list[str] = []

        snippet = result.snippet.strip()
        total_context_chars = sum(len(chunk.text.strip()) for chunk in (url_source.chunks if url_source else []))
        fallback_only = bool(url_source) and bool(url_source.metadata.get("fallback"))
        if not snippet:
            score -= 4
            reasons.append("missing_snippet")
        elif len(snippet) < THIN_SNIPPET_CHAR_THRESHOLD:
            score -= 2
            reasons.append("thin_snippet")

        if heuristic_signals.relevance_hint < 0.05:
            score -= 3
            reasons.append("very_low_relevance")
        elif heuristic_signals.relevance_hint < 0.12:
            score -= 1
            reasons.append("low_relevance")
        elif heuristic_signals.relevance_hint >= 0.3:
            score += 2
            reasons.append("good_relevance")

        if fallback_only:
            score -= 3
            reasons.append("fallback_only_context")
            if not snippet or len(snippet) < THIN_SNIPPET_CHAR_THRESHOLD:
                score -= 2
                reasons.append("fallback_only_thin_source")
            if total_context_chars < VERY_THIN_FALLBACK_CONTEXT_CHAR_THRESHOLD:
                score -= 1
                reasons.append("very_thin_fallback_context")
        if total_context_chars < THIN_CONTEXT_CHAR_THRESHOLD:
            score -= 2
            reasons.append("thin_context")
        elif total_context_chars >= 240:
            score += 1
            reasons.append("substantial_context")

        if has_low_quality_host_marker(str(result.url)):
            score -= 3
            reasons.append("low_quality_host")
            if fallback_only or not snippet:
                score -= 2
                reasons.append("low_quality_host_with_weak_content")

        result_path = path(str(result.url))
        if len(result_path) > LONG_PATH_CHAR_THRESHOLD or path_segment_count(str(result.url)) > LONG_PATH_SEGMENT_THRESHOLD:
            score -= 1
            reasons.append("spammy_path")

        if score <= -3:
            quality = SourceQuality.LOW
        elif score >= 2:
            quality = SourceQuality.HIGH
        else:
            quality = SourceQuality.MEDIUM

        return QualityHeuristicAssessment(
            quality=quality,
            confidence=_confidence_from_score(score=score, quality=quality),
            reasons=reasons,
        )


def _confidence_from_score(*, score: int, quality: SourceQuality) -> float:
    if quality == SourceQuality.LOW:
        return min(0.98, 0.55 + (abs(score) * 0.1))
    if quality == SourceQuality.HIGH:
        return min(0.95, 0.5 + (score * 0.08))
    margin = min(abs(score - 1), abs(score + 2))
    return max(0.45, min(0.78, 0.45 + (margin * 0.08)))
