from __future__ import annotations

from backend.app.contracts import (
    HeuristicSourceSignals,
    OfficialityLevel,
    RetrievedSourcesOutput,
    SearchResultItem,
    SourceQuality,
)
from backend.app.stages.assessor.models import HeuristicSourceAssessment
from backend.app.stages.assessor.officiality_heuristics_assessor import OfficialityHeuristicsAssessor
from backend.app.stages.assessor.quality_heuristics_assessor import QualityHeuristicsAssessor


LOW_QUALITY_DROP_CONFIDENCE = 0.8
MEDIUM_THIRD_PARTY_DROP_CONFIDENCE = 0.65
WEAK_THIRD_PARTY_DROP_CONFIDENCE = 0.62


class HeuristicSourceAssessor:
    def __init__(
        self,
        quality_assessor: QualityHeuristicsAssessor | None = None,
        officiality_assessor: OfficialityHeuristicsAssessor | None = None,
    ) -> None:
        self.quality_assessor = quality_assessor or QualityHeuristicsAssessor()
        self.officiality_assessor = officiality_assessor or OfficialityHeuristicsAssessor()

    def assess(
        self,
        *,
        result: SearchResultItem,
        retrieved_sources_output: RetrievedSourcesOutput,
        heuristic_signals: HeuristicSourceSignals,
        candidate_names: list[str],
    ) -> HeuristicSourceAssessment:
        url_source = _url_source_for_result(result=result, retrieved_sources_output=retrieved_sources_output)
        quality = self.quality_assessor.assess(
            result=result,
            url_source=url_source,
            heuristic_signals=heuristic_signals,
        )
        if quality.quality == SourceQuality.LOW and quality.confidence >= LOW_QUALITY_DROP_CONFIDENCE:
            return HeuristicSourceAssessment(
                quality=quality,
                officiality=self.officiality_assessor.assess(result=result, candidate_names=candidate_names),
                filtered_out=True,
                filter_reason="low_quality",
            )

        officiality = self.officiality_assessor.assess(
            result=result,
            candidate_names=candidate_names,
        )
        if (
            quality.quality == SourceQuality.MEDIUM
            and officiality.officiality == OfficialityLevel.THIRD_PARTY
            and quality.confidence >= MEDIUM_THIRD_PARTY_DROP_CONFIDENCE
            and officiality.confidence >= MEDIUM_THIRD_PARTY_DROP_CONFIDENCE
        ):
            return HeuristicSourceAssessment(
                quality=quality,
                officiality=officiality,
                filtered_out=True,
                filter_reason="medium_quality_third_party",
            )
        if (
            quality.quality == SourceQuality.MEDIUM
            and officiality.officiality in {OfficialityLevel.THIRD_PARTY, None}
            and "fallback_only_context" in quality.reasons
            and (
                "thin_context" in quality.reasons
                or "thin_snippet" in quality.reasons
                or "very_low_relevance" in quality.reasons
            )
            and quality.confidence >= WEAK_THIRD_PARTY_DROP_CONFIDENCE
        ):
            return HeuristicSourceAssessment(
                quality=quality,
                officiality=officiality,
                filtered_out=True,
                filter_reason="weak_third_party_source",
            )

        return HeuristicSourceAssessment(
            quality=quality,
            officiality=officiality,
            filtered_out=False,
            filter_reason=None,
        )


def _url_source_for_result(
    *,
    result: SearchResultItem,
    retrieved_sources_output: RetrievedSourcesOutput,
):
    for url_source in retrieved_sources_output.url_sources:
        if url_source.url == result.url:
            return url_source
    return None
