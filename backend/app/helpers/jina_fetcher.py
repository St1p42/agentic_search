from __future__ import annotations

"""Jina fetch helper owned by the orchestrator."""

import re
from typing import Protocol

from backend.app.api_clients import HttpJinaReaderClient, JinaReaderClient
from backend.app.config import JinaFetcherRuntimeConfig, load_jina_fetcher_runtime_config
from backend.app.contracts import (
    AssessorOutput,
    DeepFetchedDocument,
    EvidenceOrigin,
    JinaFetcherOutput,
    RetrievedChunk,
    UrlSource,
)


SECTION_SPLIT_PATTERN = re.compile(r"\n{2,}|(?=\n#{1,4}\s+)")
SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?](?:\s+|$)")
CLAUSE_BOUNDARY_PATTERN = re.compile(r"[;,](?:\s+|$)")
MIN_TAIL_CHARS_FRACTION = 0.2
TAIL_SPLIT_SEARCH_MARGIN_CHARS = 100

class JinaFetcher(Protocol):
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        """Fetch selected Jina pages and return page text/chunks/failure markers."""


class PlaceholderJinaFetcher:
    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        _ = assessor_output
        _ = remaining_fetch_budget
        return JinaFetcherOutput(fetched_documents=[])


class DefaultJinaFetcher:
    def __init__(
        self,
        runtime_config: JinaFetcherRuntimeConfig | None = None,
        jina_reader_client: JinaReaderClient | None = None,
    ) -> None:
        self._runtime_config = runtime_config
        self._jina_reader_client = jina_reader_client

    def run(
        self,
        assessor_output: AssessorOutput,
        remaining_fetch_budget: int,
    ) -> JinaFetcherOutput:
        config = self._config()
        selected_urls = assessor_output.selected_jina_urls[: max(0, remaining_fetch_budget)]
        fetched_documents: list[DeepFetchedDocument] = []
        url_sources: list[UrlSource] = []

        for selected_url in selected_urls:
            try:
                document = self._client().fetch_url(url=str(selected_url))
                source_id = _source_id(origin=EvidenceOrigin.JINA, source_url=str(selected_url))
                chunks = chunk_document_text(
                    document.text,
                    source_id=source_id,
                    max_chunks=config.max_chunks_per_doc,
                    max_chars_per_chunk=config.max_chars_per_chunk,
                )
                fetched_documents.append(
                    DeepFetchedDocument(
                        url=selected_url,
                        title=document.title,
                        text=document.text,
                        chunks=chunks,
                        fetch_succeeded=True,
                        error_message=None,
                    )
                )
                url_sources.append(
                    UrlSource(
                        source_id=source_id,
                        url=selected_url,
                        title=document.title,
                        origin=EvidenceOrigin.JINA,
                        chunks=chunks,
                    )
                )
            except Exception as exc:
                fetched_documents.append(
                    DeepFetchedDocument(
                        url=selected_url,
                        title=str(selected_url),
                        text=None,
                        chunks=[],
                        fetch_succeeded=False,
                        error_message=str(exc),
                    )
                )
                url_sources.append(
                    UrlSource(
                        source_id=_source_id(origin=EvidenceOrigin.JINA, source_url=str(selected_url)),
                        url=selected_url,
                        title=str(selected_url),
                        origin=EvidenceOrigin.JINA,
                        metadata={"fetch_succeeded": False, "error_message": str(exc)},
                        chunks=[],
                    )
                )

        return JinaFetcherOutput(fetched_documents=fetched_documents, url_sources=url_sources)

    def _config(self) -> JinaFetcherRuntimeConfig:
        return self._runtime_config or load_jina_fetcher_runtime_config()

    def _client(self) -> JinaReaderClient:
        if self._jina_reader_client is not None:
            return self._jina_reader_client

        config = self._config()
        self._jina_reader_client = HttpJinaReaderClient(
            base_url=config.reader_base_url,
            api_key=config.jina_api_key,
            timeout_seconds=config.timeout_seconds,
        )
        return self._jina_reader_client


def build_jina_fetcher(
    runtime_config: JinaFetcherRuntimeConfig | None = None,
    jina_reader_client: JinaReaderClient | None = None,
) -> JinaFetcher:
    config = runtime_config or load_jina_fetcher_runtime_config()
    if config.mode == "placeholder":
        return PlaceholderJinaFetcher()
    if config.mode == "jina":
        return DefaultJinaFetcher(
            runtime_config=config,
            jina_reader_client=jina_reader_client,
        )
    raise ValueError(f"Unsupported Jina fetcher mode: {config.mode}")


def chunk_document_text(
    text: str,
    *,
    source_id: str,
    max_chunks: int,
    max_chars_per_chunk: int,
) -> list[RetrievedChunk]:
    normalized_text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if not normalized_text:
        return []

    # Split on paragraph breaks (`\n\n+`) or before markdown headings (`\n# ...`)
    # so each chunk tends to preserve coherent section boundaries.
    sections = [
        section.strip()
        for section in SECTION_SPLIT_PATTERN.split(normalized_text)
        if section.strip()
    ]
    chunks: list[RetrievedChunk] = []
    current_chunk = ""
    next_sequence_index = 0

    for section in sections:
        for section_part in _split_oversized_section(
            section,
            max_chars_per_chunk=max_chars_per_chunk,
        ):
            if not current_chunk:
                current_chunk = section_part
                continue
            if len(current_chunk) + len(section_part) + 2 <= max_chars_per_chunk:
                current_chunk = f"{current_chunk}\n\n{section_part}"
                continue
            chunks.append(
                _retrieved_chunk(
                    source_id=source_id,
                    text=current_chunk.strip(),
                    sequence_index=next_sequence_index,
                )
            )
            next_sequence_index += 1
            if len(chunks) >= max_chunks:
                return chunks
            current_chunk = section_part

    if current_chunk and len(chunks) < max_chunks:
        chunks.append(
            _retrieved_chunk(
                source_id=source_id,
                text=current_chunk.strip(),
                sequence_index=next_sequence_index,
            )
        )

    return chunks[:max_chunks]


def _retrieved_chunk(
    *,
    source_id: str,
    text: str,
    sequence_index: int,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"{source_id}#{sequence_index}",
        source_id=source_id,
        text=text,
        sequence_index=sequence_index,
    )


def _source_id(*, origin: EvidenceOrigin, source_url: str) -> str:
    return f"{origin.value}:{source_url}"


def _split_oversized_section(section: str, *, max_chars_per_chunk: int) -> list[str]:
    section = section.strip()
    if len(section) <= max_chars_per_chunk:
        return [section]

    parts: list[str] = []
    remaining_text = section
    min_tail_chars = max(1, int(max_chars_per_chunk * MIN_TAIL_CHARS_FRACTION))

    while len(remaining_text) > max_chars_per_chunk:
        split_at = _best_split_index(
            remaining_text,
            max_chars_per_chunk=max_chars_per_chunk,
            min_tail_chars=min_tail_chars,
        )
        parts.append(remaining_text[:split_at].strip())
        remaining_text = remaining_text[split_at:].strip()

    if remaining_text:
        parts.append(remaining_text)

    return parts


def _best_split_index(
    text: str,
    *,
    max_chars_per_chunk: int,
    min_tail_chars: int,
) -> int:
    split_upper_bound = min(
        max_chars_per_chunk,
        max(1, len(text) - min_tail_chars),
    )
    split_lower_bound = max(1, split_upper_bound - TAIL_SPLIT_SEARCH_MARGIN_CHARS)
    window = text[: split_upper_bound + 1]

    sentence_match_end = _last_pattern_match_end(
        pattern=SENTENCE_BOUNDARY_PATTERN,
        text=window,
        lower_bound=split_lower_bound,
    )
    if sentence_match_end is not None:
        return sentence_match_end

    clause_match_end = _last_pattern_match_end(
        pattern=CLAUSE_BOUNDARY_PATTERN,
        text=window,
        lower_bound=split_lower_bound,
    )
    if clause_match_end is not None:
        return clause_match_end

    whitespace_index = window.rfind(" ", split_lower_bound)
    if whitespace_index >= split_lower_bound:
        return whitespace_index + 1

    return split_upper_bound


def _last_pattern_match_end(
    *,
    pattern: re.Pattern[str],
    text: str,
    lower_bound: int,
) -> int | None:
    match_end: int | None = None
    for match in pattern.finditer(text):
        if match.end() >= lower_bound:
            match_end = match.end()
    return match_end
