from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.contracts import OfficialityLevel, SourceQuality


@dataclass(frozen=True)
class QualityHeuristicAssessment:
    quality: SourceQuality
    confidence: float
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OfficialityHeuristicAssessment:
    officiality: OfficialityLevel | None
    confidence: float
    reasons: list[str] = field(default_factory=list)

    @property
    def is_ambiguous(self) -> bool:
        return self.officiality is None


@dataclass(frozen=True)
class HeuristicSourceAssessment:
    quality: QualityHeuristicAssessment
    officiality: OfficialityHeuristicAssessment
    filtered_out: bool
    filter_reason: str | None = None
