from __future__ import annotations

from backend.app.contracts import OfficialityLevel, SearchResultItem
from backend.app.stages.assessor.models import OfficialityHeuristicAssessment
from backend.app.stages.assessor.utils import (
    has_official_path,
    has_third_party_pattern,
    hostname_core,
    normalize_compact,
)


class OfficialityHeuristicsAssessor:
    def assess(
        self,
        *,
        result: SearchResultItem,
        candidate_names: list[str],
    ) -> OfficialityHeuristicAssessment:
        reasons: list[str] = []
        domain_core = hostname_core(str(result.url))
        title_normalized = normalize_compact(result.title)
        snippet_normalized = normalize_compact(result.snippet)
        path_match = has_official_path(str(result.url))

        best_domain_match = 0.0
        best_title_match = 0.0
        for candidate_name in candidate_names:
            normalized_candidate = normalize_compact(candidate_name)
            if len(normalized_candidate) < 4:
                continue
            best_domain_match = max(best_domain_match, _compact_overlap(normalized_candidate, domain_core))
            title_match = max(
                _contains_ratio(normalized_candidate, title_normalized),
                _contains_ratio(normalized_candidate, snippet_normalized),
            )
            best_title_match = max(best_title_match, title_match)

        if best_domain_match >= 0.92 and best_title_match >= 0.92 and not has_third_party_pattern(
            result.title,
            result.snippet,
            str(result.url),
        ):
            reasons.extend(["strong_domain_match", "strong_title_match"])
            return OfficialityHeuristicAssessment(
                officiality=OfficialityLevel.OFFICIAL,
                confidence=0.94,
                reasons=reasons,
            )

        if (
            (best_domain_match >= 0.78 and best_title_match >= 0.72)
            or (path_match and best_title_match >= 0.72)
        ):
            if path_match:
                reasons.append("official_path")
            if best_domain_match >= 0.78:
                reasons.append("moderate_domain_match")
            if best_title_match >= 0.72:
                reasons.append("title_or_snippet_match")
            return OfficialityHeuristicAssessment(
                officiality=OfficialityLevel.NEAR_OFFICIAL,
                confidence=0.78 if path_match else 0.74,
                reasons=reasons,
            )

        if (
            has_third_party_pattern(result.title, result.snippet, str(result.url))
            and best_domain_match < 0.78
            and best_title_match < 0.72
        ):
            reasons.append("editorial_or_directory_pattern")
            return OfficialityHeuristicAssessment(
                officiality=OfficialityLevel.THIRD_PARTY,
                confidence=0.8,
                reasons=reasons,
            )

        return OfficialityHeuristicAssessment(
            officiality=None,
            confidence=0.35,
            reasons=["ambiguous_source_type"],
        )


def _compact_overlap(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right))
    shared = sum(1 for char in set(left) if char in right)
    return shared / max(len(set(left)), 1)


def _contains_ratio(needle: str, haystack: str) -> float:
    if not needle or not haystack:
        return 0.0
    if needle in haystack:
        return 1.0
    return _compact_overlap(needle, haystack)
