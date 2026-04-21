from __future__ import annotations

"""Passive JSONL accumulation for source-bucket training data."""

import json
from pathlib import Path
from typing import Protocol, TypedDict

from backend.app.contracts import PlannerOutput, SearchResultItem
from backend.app.helpers.source_bucket_classifier import DEFAULT_SOURCE_BUCKET_MODEL, SourceBucketDecision


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_BUCKET_DATASET_PATH = REPO_ROOT / "backend" / "evals" / "source_bucket_dataset.jsonl"


class SourceBucketDatasetWriter(Protocol):
    def write(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
        decisions_by_url: dict[str, SourceBucketDecision],
    ) -> None:
        """Append unseen source bucket rows to the dataset."""


class SourceBucketRow(TypedDict):
    normalized_query: str
    base_query: str
    query_rewrites: list[str]
    url: str
    title: str
    snippet: str
    query_sources: list[str]
    rank: int
    bucket: str
    bucket_confidence: float
    bucket_reason: str
    judge_model: str


class JsonlSourceBucketDatasetWriter(SourceBucketDatasetWriter):
    def __init__(self, dataset_path: Path | None = None, judge_model: str = DEFAULT_SOURCE_BUCKET_MODEL) -> None:
        self._dataset_path = dataset_path or DEFAULT_SOURCE_BUCKET_DATASET_PATH
        self._judge_model = judge_model

    def write(
        self,
        *,
        planner_output: PlannerOutput,
        search_results: list[SearchResultItem],
        decisions_by_url: dict[str, SourceBucketDecision],
    ) -> None:
        if not search_results or not decisions_by_url:
            return

        rows = [
            _row(
                planner_output=planner_output,
                search_result=search_result,
                decision=decisions_by_url.get(str(search_result.url)),
                judge_model=self._judge_model,
            )
            for search_result in search_results
            if str(search_result.url) in decisions_by_url
        ]
        if not rows:
            return

        dataset_path = self._dataset_path
        dataset_path.parent.mkdir(parents=True, exist_ok=True)
        existing_keys = _existing_keys(dataset_path)
        with dataset_path.open("a", encoding="utf-8") as handle:
            for row in rows:
                dedupe_key = _dedupe_key(normalized_query=row["normalized_query"], url=row["url"])
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
            keys.add(_dedupe_key(normalized_query=str(record.get("normalized_query", "")), url=str(record.get("url", ""))))
    return keys


def _row(
    *,
    planner_output: PlannerOutput,
    search_result: SearchResultItem,
    decision: SourceBucketDecision | None,
    judge_model: str,
) -> SourceBucketRow:
    return {
        "normalized_query": planner_output.normalized_query,
        "base_query": planner_output.base_query,
        "query_rewrites": list(planner_output.initial_query_rewrites),
        "url": str(search_result.url),
        "title": search_result.title,
        "snippet": search_result.snippet,
        "query_sources": list(search_result.query_sources),
        "rank": search_result.rank,
        "bucket": decision.bucket if decision is not None else "editorial_reference",
        "bucket_confidence": decision.confidence if decision is not None else 0.0,
        "bucket_reason": decision.reason if decision is not None else "",
        "judge_model": judge_model,
    }


def _dedupe_key(*, normalized_query: str, url: str) -> str:
    return f"{normalized_query}\u241f{url}"
