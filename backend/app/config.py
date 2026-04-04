from __future__ import annotations

"""Small environment-backed runtime settings loader."""

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = REPO_ROOT / ".env"

DEFAULT_PLANNER_MODEL = "gpt-5-mini"
DEFAULT_PLANNER_MODE = "llm"
ENV_OPENAI_API_KEY = "OPENAI_API_KEY"
ENV_PLANNER_MODE = "PLANNER_MODE"
ENV_PLANNER_MODEL = "PLANNER_MODEL"


@dataclass(frozen=True)
class PlannerRuntimeConfig:
    model: str = DEFAULT_PLANNER_MODEL
    mode: str = DEFAULT_PLANNER_MODE
    openai_api_key: str | None = None


def _load_env_file(env_path: Path = DEFAULT_ENV_PATH) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_planner_runtime_config(env_path: Path = DEFAULT_ENV_PATH) -> PlannerRuntimeConfig:
    _load_env_file(env_path)
    return PlannerRuntimeConfig(
        model=os.getenv(ENV_PLANNER_MODEL, DEFAULT_PLANNER_MODEL).strip() or DEFAULT_PLANNER_MODEL,
        mode=os.getenv(ENV_PLANNER_MODE, DEFAULT_PLANNER_MODE).strip() or DEFAULT_PLANNER_MODE,
        openai_api_key=os.getenv(ENV_OPENAI_API_KEY),
    )
