from __future__ import annotations

"""SSE event contracts for pipeline lifecycle streaming and UI-facing stage summaries."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.app.contracts.errors import PipelineError


class SseEventName(str, Enum):
    RUN_STARTED = "run_started"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"
    REPAIR_STARTED = "repair_started"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class StageMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    value: int | str


class StageUiDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    metrics: list[StageMetric] = Field(default_factory=list)


class SchemaPreviewColumnUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    label: str
    type: Literal["text", "url", "number", "date"] = "text"


class SchemaPreviewUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    columns: list[SchemaPreviewColumnUiModel] = Field(default_factory=list)


class StartedSearchStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(summary="Preparing research pipeline")


class PlanningStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interpreted_query: str
    columns_selected: int
    schema_preview: SchemaPreviewUiModel

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Set up the search and selected the result columns",
            metrics=[
                StageMetric(key="lookingFor", label="Looking for", value=self.interpreted_query),
                StageMetric(key="columnsSelected", label="Columns selected", value=self.columns_selected),
            ],
        )


class RetrievingSourcesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queries_run: int
    sources_found: int
    shortlisted: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Searched the web and gathered candidate sources",
            metrics=[
                StageMetric(key="queriesRun", label="Queries run", value=self.queries_run),
                StageMetric(key="sourcesFound", label="Sources found", value=self.sources_found),
                StageMetric(key="shortlisted", label="Shortlisted", value=self.shortlisted),
            ],
        )


class ProcessingSourcesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources_processed: int
    relevant_details_found: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Pulled relevant source details for analysis",
            metrics=[
                StageMetric(key="sourcesProcessed", label="Sources deep-fetched", value=self.sources_processed),
                StageMetric(
                    key="relevantDetailsFound",
                    label="Relevant details found",
                    value=self.relevant_details_found,
                ),
            ],
        )


class SelectingSourcePassagesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passages_scored: int
    passages_selected: int
    sources_represented: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Picked the most relevant passages from fetched sources",
            metrics=[
                StageMetric(key="passagesScored", label="Passages scored", value=self.passages_scored),
                StageMetric(key="passagesSelected", label="Passages selected", value=self.passages_selected),
                StageMetric(key="sourcesRepresented", label="Sources represented", value=self.sources_represented),
            ],
        )


class ClassifyingSourcesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    official_sources: int
    profile_sources: int
    roundup_sources: int
    editorial_reference_sources: int
    transactional_sources: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Grouped shortlisted sources by source type",
            metrics=[
                StageMetric(key="officialSources", label="Official sources", value=self.official_sources),
                StageMetric(key="profileSources", label="Profile sources", value=self.profile_sources),
                StageMetric(key="roundupSources", label="Roundup sources", value=self.roundup_sources),
                StageMetric(
                    key="editorialReferenceSources",
                    label="Editorial/reference sources",
                    value=self.editorial_reference_sources,
                ),
                StageMetric(key="transactionalSources", label="Transactional sources", value=self.transactional_sources),
            ],
        )


class IdentifyingCandidatesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preliminary_candidates: int
    mentions_found: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Found possible entities mentioned across sources",
            metrics=[
                StageMetric(
                    key="preliminaryCandidates",
                    label="Preliminary candidates",
                    value=self.preliminary_candidates,
                ),
                StageMetric(key="mentionsFound", label="Mentions found", value=self.mentions_found),
            ],
        )


class AssessingSourceQualityStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources_assessed: int
    heuristic_filtered_sources: int
    sources_sent_to_llm: int
    sources_kept_for_analysis: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Filtered for sources strong enough to keep using",
            metrics=[
                StageMetric(key="sourcesAssessed", label="Sources assessed", value=self.sources_assessed),
                StageMetric(
                    key="heuristicFilteredSources",
                    label="Heuristic-filtered sources",
                    value=self.heuristic_filtered_sources,
                ),
                StageMetric(
                    key="sourcesSentToLlm",
                    label="Sources sent to LLM",
                    value=self.sources_sent_to_llm,
                ),
                StageMetric(
                    key="sourcesKeptForAnalysis",
                    label="Sources kept for analysis",
                    value=self.sources_kept_for_analysis,
                ),
            ],
        )


class HeuristicAssessingSourceQualityStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources_reviewed: int
    filtered_out: int
    used_for_evidence: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Reviewed sources and kept the strongest evidence",
            metrics=[
                StageMetric(key="sourcesReviewed", label="Sources reviewed", value=self.sources_reviewed),
                StageMetric(key="filteredOut", label="Filtered out", value=self.filtered_out),
                StageMetric(key="usedForEvidence", label="Used for evidence", value=self.used_for_evidence),
            ],
        )


class RetrievingEvidenceStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates_with_evidence: int
    supporting_sources_linked: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Collected supporting evidence for likely results",
            metrics=[
                StageMetric(
                    key="candidatesWithEvidence",
                    label="Candidates with evidence",
                    value=self.candidates_with_evidence,
                ),
                StageMetric(
                    key="supportingSourcesLinked",
                    label="Supporting sources linked",
                    value=self.supporting_sources_linked,
                ),
            ],
        )


class RankingCandidatesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    core_candidates_kept: int
    discovery_candidates_kept: int
    core_candidates_filtered: int
    discovery_candidates_filtered: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Filtered and ranked candidates before profile building",
            metrics=[
                StageMetric(key="coreCandidatesKept", label="Core candidates kept", value=self.core_candidates_kept),
                StageMetric(
                    key="discoveryCandidatesKept",
                    label="Discovery candidates kept",
                    value=self.discovery_candidates_kept,
                ),
                StageMetric(
                    key="coreCandidatesFiltered",
                    label="Core candidates filtered",
                    value=self.core_candidates_filtered,
                ),
                StageMetric(
                    key="discoveryCandidatesFiltered",
                    label="Discovery candidates filtered",
                    value=self.discovery_candidates_filtered,
                ),
            ],
        )


class BuildingEntitiesStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles_built: int
    missing_fields: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Built structured profiles from the collected evidence",
            metrics=[
                StageMetric(key="profilesBuilt", label="Profiles built", value=self.profiles_built),
                StageMetric(key="missingFields", label="Missing fields", value=self.missing_fields),
            ],
        )


class FinalizingTableStageUiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows_ready: int

    def to_ui_details(self) -> StageUiDetails:
        return StageUiDetails(
            summary="Prepared the final set of results",
            metrics=[StageMetric(key="rowsReady", label="Rows ready", value=self.rows_ready)],
        )


class EventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    stage: str | None = None
    message: str
    data: dict[str, object] = Field(default_factory=dict)
    error: PipelineError | None = None


class SseEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: SseEventName
    payload: EventPayload
    schema_version: Literal["1.0"] = "1.0"
