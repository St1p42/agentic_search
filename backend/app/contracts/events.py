from __future__ import annotations

"""SSE event contracts for pipeline lifecycle streaming."""

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
