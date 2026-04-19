from __future__ import annotations

"""Passive JSONL accumulation for Jina chunk relevance evaluation."""

import json
import re
from pathlib import Path
from typing import Protocol, TypedDict

from backend.app.contracts import PlannerOutput, UrlSource


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JINA_EVAL_DATASET_PATH = REPO_ROOT / "backend" / "evals" / "jina_chunk_eval.jsonl"
WHITESPACE_PATTERN = re.compile(r"\s+")


class JinaEvalDatasetWriter(Protocol):
    def write(
        self,
        *,
        request_query: str,
        planner_output: PlannerOutput,
        url_sources: list[UrlSource],
    ) -> None:
        """Append unseen `(normalized_query, source_url, chunk_text)` rows to the eval dataset."""


class JinaEvalRow(TypedDict):
    request_query: str
    normalized_query: str
    base_query: str
    query_rewrites: list[str]
    query_variants: list[str]
    source_url: str
    source_title: str
    chunk_id: str
    chunk_text: str
    origin: str
    relevance: int | None
    judge_model: str | None
    label_reason: str | None


class JsonlJinaEvalDatasetWriter:
    def __init__(self, dataset_path: Path | None = None) -> None:
        self._dataset_path = dataset_path or DEFAULT_JINA_EVAL_DATASET_PATH

    def write(
        self,
        *,
        request_query: str,
        planner_output: PlannerOutput,
        url_sources: list[UrlSource],
    ) -> None:
        rows = [
            _row(
                request_query=request_query,
                planner_output=planner_output,
                url_source=url_source,
                chunk_text=chunk.text,
                chunk_id=chunk.chunk_id,
            )
            for url_source in url_sources
            for chunk in url_source.chunks
            if chunk.text.strip()
        ]
        if not rows:
            return

        dataset_path = self._dataset_path
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        existing_keys = _existing_keys(dataset_path)

        with dataset_path.open("a", encoding="utf-8") as handle:
            for row in rows:
                dedupe_key = _dedupe_key(
                    normalized_query=row["normalized_query"],
                    source_url=row["source_url"],
                    chunk_text=row["chunk_text"],
                )
                if dedupe_key in existing_keys:
                    continue
                handle.write(json.dumps(row, ensure_ascii=True) + "\n")
                existing_keys.add(dedupe_key)


def _existing_keys(dataset_path: Path) -> set[str]:
    if not dataset_path.exists():
        return set()

    keys: set[str] = set()
    with dataset_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            record = json.loads(line)
            keys.add(
                _dedupe_key(
                    normalized_query=str(record.get("normalized_query", "")),
                    source_url=str(record.get("source_url", "")),
                    chunk_text=str(record.get("chunk_text", "")),
                )
            )
    return keys


def _row(
    *,
    request_query: str,
    planner_output: PlannerOutput,
    url_source: UrlSource,
    chunk_text: str,
    chunk_id: str,
) -> JinaEvalRow:
    query_variants: list[str] = []
    for query in [
        planner_output.normalized_query,
        planner_output.base_query,
        *planner_output.initial_query_rewrites,
    ]:
        normalized_query = " ".join(query.split())
        if normalized_query and normalized_query not in query_variants:
            query_variants.append(normalized_query)
    return {
        "request_query": request_query,
        "normalized_query": planner_output.normalized_query,
        "base_query": planner_output.base_query,
        "query_rewrites": list(planner_output.initial_query_rewrites),
        "query_variants": query_variants,
        "source_url": str(url_source.url),
        "source_title": url_source.title,
        "chunk_id": chunk_id,
        "chunk_text": chunk_text,
        "origin": url_source.origin.value,
        "relevance": None,
        "judge_model": None,
        "label_reason": None,
    }


def _dedupe_key(
    *,
    normalized_query: str,
    source_url: str,
    chunk_text: str,
) -> str:
    normalized_chunk_text = WHITESPACE_PATTERN.sub(" ", chunk_text).strip()
    return f"{normalized_query}\u241f{source_url}\u241f{normalized_chunk_text}"
