"""Stage prompt templates and constants."""

from backend.app.prompts.assessor_prompts import ASSESSOR_SYSTEM_PROMPT
from backend.app.prompts.extractor_light_prompts import EXTRACTOR_LIGHT_SYSTEM_PROMPT
from backend.app.prompts.planner_prompts import PLANNER_SYSTEM_PROMPT

__all__ = [
    "ASSESSOR_SYSTEM_PROMPT",
    "EXTRACTOR_LIGHT_SYSTEM_PROMPT",
    "PLANNER_SYSTEM_PROMPT",
]
