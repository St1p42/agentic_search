from __future__ import annotations

"""Typed error contracts shared by the controller and API layer."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    INVALID_QUERY = "invalid_query"
    PLANNER_FAILED = "planner_failed"
    SEARCH_FAILED = "search_failed"
    FETCH_FAILED = "fetch_failed"
    EXTRACT_FAILED = "extract_failed"
    FINALIZATION_FAILED = "finalization_failed"
    BUDGET_EXHAUSTED = "budget_exhausted"
    INTERNAL_ERROR = "internal_error"


class PipelineError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str
    stage: str | None = None
    details: dict[str, str] = Field(default_factory=dict)
