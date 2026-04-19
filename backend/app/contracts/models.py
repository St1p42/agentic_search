from __future__ import annotations

"""Core typed contracts for the deterministic multi-stage pipeline."""

from enum import Enum
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, model_validator


DEFAULT_MAX_TOTAL_SEARCH_ROUNDS = 2
DEFAULT_MAX_SEARCH_QUERIES = 4
DEFAULT_MAX_VERIFICATION_QUERIES = 7
DEFAULT_MAX_SHORTLISTED_URLS = 15
DEFAULT_MAX_DEEP_FETCHES = 7
DEFAULT_MAX_REPAIR_ROUNDS = 1
DEFAULT_MAX_FINAL_ROWS = 10


class StageName(str, Enum):
    PLANNER = "planner"
    SEARCHER = "searcher"
    EXTRACTOR_LIGHT = "extractor_light"
    ASSESSOR = "assessor"
    EXTRACTOR = "extractor"
    FINALIZER = "finalizer"


class AssessorPass(str, Enum):
    FIRST_PASS = "first_pass"
    VERIFICATION_PASS = "verification_pass"
    JINA_SELECTION = "jina_selection"


class SourceRole(str, Enum):
    DISCOVERY = "discovery"
    VERIFICATION = "verification"
    CORROBORATION = "corroboration"


class SourceQuality(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class OfficialityLevel(str, Enum):
    OFFICIAL = "official"
    NEAR_OFFICIAL = "near_official"
    THIRD_PARTY = "third_party"
    LOW_QUALITY = "low_quality"


class EvidenceOrigin(str, Enum):
    BRAVE_LLM = "brave_llm"
    JINA = "jina"


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl
    source_title: str
    supporting_snippet: str
    source_role: SourceRole = SourceRole.DISCOVERY
    source_quality: SourceQuality = SourceQuality.MEDIUM
    officiality: OfficialityLevel = OfficialityLevel.THIRD_PARTY


class FieldValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | int | float | bool | list[str] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_evidence_for_non_null_values(self) -> FieldValue:
        if self.value is not None and not self.evidence:
            raise ValueError("non-null field values must include supporting evidence")
        return self


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_type: str
    query_mode: str
    schema_columns: list[str] = Field(min_length=1, max_length=10)
    core_aspects: list[str] = Field(min_length=1, max_length=10)
    base_query: str
    initial_query_rewrites: list[str] = Field(default_factory=list, max_length=3)
    is_topic_query: bool
    normalized_query: str
    normalization_note: str | None = None
    error: bool = False
    error_message: str | None = None


class SearchResultItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    title: str
    snippet: str
    domain: str
    rank: int = Field(ge=1)
    query_sources: list[str] = Field(default_factory=list)
    result_type: str | None = None
    provider_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class SearcherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executed_queries: list[str]
    raw_results: list[SearchResultItem]
    shortlisted_results: list[SearchResultItem]


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    source_id: str
    text: str
    sequence_index: int = Field(ge=0)


class UrlSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    url: HttpUrl
    title: str
    origin: EvidenceOrigin
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    chunks: list[RetrievedChunk] = Field(default_factory=list)


class DeepFetchedDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrl
    title: str
    text: str | None = None
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    fetch_succeeded: bool = True
    error_message: str | None = None


class BraveContextPassage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_url: HttpUrl
    passage_text: str
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class BraveContextOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    passages_by_url: dict[HttpUrl, list[BraveContextPassage]] = Field(default_factory=dict)
    retrieved_chunks_by_url: dict[HttpUrl, list[RetrievedChunk]] = Field(default_factory=dict)
    url_sources: list[UrlSource] = Field(default_factory=list)


class HeuristicSourceSignals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance_hint: float = Field(ge=0.0, le=1.0)
    domain_match_hint: float = Field(ge=0.0, le=1.0)
    official_path_hint: float = Field(ge=0.0, le=1.0)
    snippet_thinness_hint: float = Field(ge=0.0, le=1.0)
    rank_hint: int = Field(ge=1)
    source_metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class AssessedSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: SearchResultItem
    brave_context_passages: list[BraveContextPassage] = Field(default_factory=list)
    heuristic_signals: HeuristicSourceSignals
    source_role: SourceRole = SourceRole.DISCOVERY
    source_quality: SourceQuality = SourceQuality.MEDIUM
    officiality: OfficialityLevel = OfficialityLevel.THIRD_PARTY
    estimated_aspect_coverage: list[str] = Field(default_factory=list)
    evidence_sufficiency: float = Field(ge=0.0, le=1.0)
    should_deep_fetch: bool
    fetch_reason: str | None = None
    filtered_out: bool = False


class ExtractorLightOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_names: list[str] = Field(default_factory=list)
    name_to_source_urls: dict[str, list[HttpUrl]] = Field(default_factory=dict)
    mention_counts: dict[str, int] = Field(default_factory=dict)


class EntityVerificationGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_name: str
    mention_count: int = Field(ge=0)
    suggested_query: str


class AssessorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_type: AssessorPass = AssessorPass.FIRST_PASS
    assessed_sources: list[AssessedSource]
    verification_gaps: list[EntityVerificationGap] = Field(default_factory=list)
    selected_jina_urls: list[HttpUrl] = Field(default_factory=list)


class EvidenceChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    source_url: HttpUrl
    source_title: str
    source_role: SourceRole
    source_quality: SourceQuality
    officiality: OfficialityLevel
    origin: EvidenceOrigin
    aspect_coverage: list[str] = Field(default_factory=list)


class EvidenceStore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks_by_entity: dict[str, list[EvidenceChunk]] = Field(default_factory=dict)
    entity_scores: dict[str, float] = Field(default_factory=dict)


class JinaFetcherOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fetched_documents: list[DeepFetchedDocument]
    url_sources: list[UrlSource] = Field(default_factory=list)


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    entity_name: str
    fields: dict[str, FieldValue]
    source_urls: list[HttpUrl] = Field(default_factory=list)
    provisional: bool = False


class ExtractorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: list[ExtractedEntity]


class CanonicalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    fields: dict[str, FieldValue]
    source_urls: list[HttpUrl] = Field(default_factory=list)


class CanonicalizerVerifierEvaluatorOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    final_rows: list[CanonicalEntity]


class BudgetState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_total_search_rounds: int = DEFAULT_MAX_TOTAL_SEARCH_ROUNDS
    max_total_search_queries: int = DEFAULT_MAX_SEARCH_QUERIES
    max_verification_queries: int = DEFAULT_MAX_VERIFICATION_QUERIES
    max_shortlisted_urls: int = DEFAULT_MAX_SHORTLISTED_URLS
    max_deep_fetches: int = DEFAULT_MAX_DEEP_FETCHES
    max_repair_rounds: int = DEFAULT_MAX_REPAIR_ROUNDS
    max_final_rows: int = DEFAULT_MAX_FINAL_ROWS
    used_search_rounds: int = 0
    used_search_queries: int = 0
    used_verification_queries: int = 0
    used_deep_fetches: int = 0
    used_repair_rounds: int = 0

    @property
    def can_repair(self) -> bool:
        return self.used_repair_rounds < self.max_repair_rounds

    @property
    def can_search(self) -> bool:
        return (
            self.used_search_rounds < self.max_total_search_rounds
            and self.used_search_queries < self.max_total_search_queries
        )

    @property
    def can_fetch(self) -> bool:
        return self.used_deep_fetches < self.max_deep_fetches

    @property
    def can_verify(self) -> bool:
        return self.used_verification_queries < self.max_verification_queries


class PipelineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    request_id: str | None = None


class PipelineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    original_query: str
    normalized_query: str
    normalization_note: str | None = None
    inferred_schema: list[str] = Field(
        validation_alias=AliasChoices("inferred_schema", "schema_columns"),
        serialization_alias="inferred_schema",
    )
    final_top_10_rows: list[CanonicalEntity] = Field(
        validation_alias=AliasChoices("final_top_10_rows", "final_rows"),
        serialization_alias="final_top_10_rows",
    )
    budget: BudgetState
    repair_used: bool
    status: Literal["completed", "failed"] = "completed"
