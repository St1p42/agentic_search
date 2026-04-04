"""Shared external API client interfaces and provider adapters."""

from backend.app.api_clients.brave_client import BraveSearchClient, BraveWebResult, HttpBraveSearchClient
from backend.app.api_clients.brave_context_client import (
    BraveLlmContextClient,
    BraveLlmContextPassage,
    HttpBraveLlmContextClient,
)
from backend.app.api_clients.jina_client import (
    HttpJinaReaderClient,
    JinaReaderClient,
    JinaReaderDocument,
)
from backend.app.api_clients.llm_client import OpenAiStructuredLlmClient, StructuredLlmClient, StructuredOutputT

__all__ = [
    "BraveLlmContextClient",
    "BraveLlmContextPassage",
    "BraveSearchClient",
    "BraveWebResult",
    "HttpBraveLlmContextClient",
    "HttpBraveSearchClient",
    "HttpJinaReaderClient",
    "JinaReaderClient",
    "JinaReaderDocument",
    "OpenAiStructuredLlmClient",
    "StructuredLlmClient",
    "StructuredOutputT",
]
