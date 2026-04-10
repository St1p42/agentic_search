from __future__ import annotations

"""Event emitter abstraction for pipeline lifecycle SSE events."""

from collections.abc import Callable

from backend.app.contracts import EventPayload, PipelineError, SseEvent, SseEventName, StageName


class PipelineEventEmitter:
    def __init__(self, sink: Callable[[SseEvent], None] | None = None) -> None:
        self._sink = sink

    def emit(
        self,
        event_name: SseEventName,
        request_id: str,
        stage: str | StageName | None,
        message: str,
        data: dict[str, object] | None = None,
        error: PipelineError | None = None,
    ) -> None:
        if self._sink is None:
            return
        self._sink(
            SseEvent(
                event=event_name,
                payload=EventPayload(
                    request_id=request_id,
                    stage=stage.value if isinstance(stage, StageName) else stage,
                    message=message,
                    data=data or {},
                    error=error,
                ),
            )
        )

    def stage_started(
        self,
        request_id: str,
        stage_name: StageName,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        self.emit(
            event_name=SseEventName.STAGE_STARTED,
            request_id=request_id,
            stage=stage_name,
            message=message,
            data=data,
        )

    def stage_completed(
        self,
        request_id: str,
        stage_name: StageName,
        message: str,
        data: dict[str, object] | None = None,
    ) -> None:
        self.emit(
            event_name=SseEventName.STAGE_COMPLETED,
            request_id=request_id,
            stage=stage_name,
            message=message,
            data=data,
        )

    def repair_started(
        self,
        request_id: str,
        followup_queries: list[str],
    ) -> None:
        self.emit(
            event_name=SseEventName.REPAIR_STARTED,
            request_id=request_id,
            stage=StageName.SEARCHER,
            message="single repair round started",
            data={"followup_queries": followup_queries},
        )
