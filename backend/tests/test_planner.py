from __future__ import annotations

from pathlib import Path
from typing import cast

from backend.app.config import (
    ENV_OPENAI_API_KEY,
    ENV_PLANNER_MODE,
    ENV_PLANNER_MODEL,
    load_planner_runtime_config,
)
from backend.app.contracts import PipelineRequest, PlannerOutput
from backend.app.llm.client import StructuredLlmClient, StructuredOutputT
from backend.app.orchestrator import PipelineOrchestrator
from backend.app.stages.planner import LlmPlannerStage, PlannerModelOutput


class FakePlannerClient:
    def __init__(self, output: PlannerModelOutput) -> None:
        self.output_payload = output.model_dump()
        self.calls: list[dict[str, str]] = []

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[StructuredOutputT],
    ) -> StructuredOutputT:
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "query": user_content,
                "response_model": response_model.__name__,
            }
        )
        return response_model.model_validate(self.output_payload)


def _as_structured_client(fake_client: FakePlannerClient) -> StructuredLlmClient:
    return cast(StructuredLlmClient, cast(object, fake_client))


def test_llm_planner_stage_returns_contract_and_json() -> None:
    fake_client = FakePlannerClient(
        PlannerModelOutput(
            entity_type="startup",
            query_mode="topic_entity_discovery",
            schema_columns=[
                "name",
                "description",
                "website",
                "focus_area",
                "location",
                "description",
            ],
            core_aspects=["clinical_focus", "product", "market_presence"],
            base_query="AI startups in healthcare",
            initial_query_rewrites=[
                "healthcare AI startups",
                "medical AI startups",
                "AI startups in healthcare",
            ],
            is_topic_query=True,
            normalized_query="AI startups in healthcare",
        )
    )
    planner = LlmPlannerStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = planner.run("  AI startups in healthcare  ")

    assert output == PlannerOutput.model_validate_json(output.model_dump_json())
    assert output.entity_type == "startup"
    assert output.schema_columns == [
        "name",
        "description",
        "website",
        "focus_area",
        "location",
    ]
    assert output.initial_query_rewrites == [
        "healthcare AI startups",
        "medical AI startups",
    ]
    assert len(output.schema_columns) == 5
    assert len(output.core_aspects) == 3
    assert fake_client.calls[0]["model"] == "gpt-5-mini"
    assert fake_client.calls[0]["query"] == "AI startups in healthcare"
    assert fake_client.calls[0]["response_model"] == "PlannerModelOutput"


def test_llm_planner_stage_rejects_non_topic_query() -> None:
    fake_client = FakePlannerClient(
        PlannerModelOutput(
            entity_type="unknown_entity",
            query_mode="invalid_query",
            schema_columns=["name", "summary", "website", "location", "category"],
            core_aspects=["identity", "relevance"],
            base_query="write me an email",
            initial_query_rewrites=[],
            is_topic_query=False,
            normalized_query="write me an email",
            error=True,
            error_message="This request asks for text generation, not entity discovery.",
        )
    )
    planner = LlmPlannerStage(
        model="gpt-5-mini",
        llm_client=_as_structured_client(fake_client),
    )

    output = planner.run("write me an email")

    assert output.error is True
    assert output.query_mode == "invalid_query"
    assert output.error_message == "This request asks for text generation, not entity discovery."


def test_llm_planner_stage_forces_name_into_schema_columns() -> None:
    fake_client = FakePlannerClient(
        PlannerModelOutput(
            entity_type="startup",
            query_mode="topic_entity_discovery",
            schema_columns=["clinical_application", "technology_type", "geographic_market", "website"],
            core_aspects=["clinical_application"],
            base_query="AI startups in healthcare",
            initial_query_rewrites=[],
            is_topic_query=True,
            normalized_query="AI startups in healthcare",
        )
    )
    planner = LlmPlannerStage(model="gpt-5-mini", llm_client=_as_structured_client(fake_client))

    output = planner.run("AI startups in healthcare")

    assert output.schema_columns[0] == "name"
    assert len(output.schema_columns) == 5
    assert output.core_aspects == ["clinical_application"]


def test_orchestrator_stream_maps_planner_rejection_to_invalid_query() -> None:
    class RejectingPlanner:
        def run(self, query: str) -> PlannerOutput:
            return PlannerOutput(
                entity_type="unknown_entity",
                query_mode="invalid_query",
                schema_columns=["name", "summary", "website", "location", "category"],
                core_aspects=["identity", "relevance"],
                base_query=query,
                initial_query_rewrites=[],
                is_topic_query=False,
                normalized_query=query,
                error=True,
                error_message="Unsupported query shape.",
            )

    orchestrator = PipelineOrchestrator(planner=RejectingPlanner())

    events = list(orchestrator.stream(PipelineRequest(query="write me an email")))

    assert events[-1].event == "run_failed"
    assert events[-1].payload.error is not None
    assert events[-1].payload.error.code == "invalid_query"
    assert events[-1].payload.error.message == "Unsupported query shape."
    assert events[-1].payload.error.stage == "planner"


def test_load_planner_runtime_config_reads_root_env_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=test-key\nPLANNER_MODE=llm\nPLANNER_MODEL=gpt-5-mini\n",
        encoding="utf-8",
    )
    monkeypatch.delenv(ENV_OPENAI_API_KEY, raising=False)
    monkeypatch.delenv(ENV_PLANNER_MODE, raising=False)
    monkeypatch.delenv(ENV_PLANNER_MODEL, raising=False)

    config = load_planner_runtime_config(env_path=env_path)

    assert config.openai_api_key == "test-key"
    assert config.mode == "llm"
    assert config.model == "gpt-5-mini"
