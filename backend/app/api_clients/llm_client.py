from __future__ import annotations

"""Shared stateless structured-output LLM adapter."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel


StructuredOutputT = TypeVar("StructuredOutputT", bound=BaseModel)

if TYPE_CHECKING:
    from openai.types.responses import EasyInputMessageParam
    from openai.types.responses.response_input_param import ResponseInputParam


class StructuredLlmClient(ABC):
    @abstractmethod
    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[StructuredOutputT],
        reasoning_effort: str | None = None,
    ) -> StructuredOutputT:
        """Parse one isolated request into one structured output object."""


class OpenAiStructuredLlmClient(StructuredLlmClient):
    def __init__(self, api_key: str) -> None:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("openai package is not installed") from exc

        self._client = OpenAI(api_key=api_key)

    def parse(
        self,
        *,
        model: str,
        system_prompt: str,
        user_content: str,
        response_model: type[StructuredOutputT],
        reasoning_effort: str | None = None,
    ) -> StructuredOutputT:
        system_message: EasyInputMessageParam = {
            "type": "message",
            "role": "system",
            "content": system_prompt,
        }
        user_message: EasyInputMessageParam = {
            "type": "message",
            "role": "user",
            "content": user_content,
        }
        request_input: ResponseInputParam = [system_message, user_message]
        response = self._client.responses.parse(
            model=model,
            input=request_input,
            text_format=response_model,
            reasoning={"effort": reasoning_effort} if reasoning_effort else None,
        )

        for output_item in response.output:
            if getattr(output_item, "type", None) != "message":
                continue
            for content_item in getattr(output_item, "content", []):
                refusal = getattr(content_item, "refusal", None)
                if refusal:
                    raise RuntimeError(refusal)
                parsed = getattr(content_item, "parsed", None)
                if parsed is not None:
                    return parsed

        raise RuntimeError("model returned no parsed structured output")
