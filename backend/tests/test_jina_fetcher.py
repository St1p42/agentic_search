from __future__ import annotations

import json
from pathlib import Path

from pydantic import HttpUrl

from backend.app.api_clients import JinaReaderClient, JinaReaderDocument
from backend.app.config import JinaFetcherRuntimeConfig
from backend.app.contracts import AssessorOutput, AssessorPass
from backend.app.helpers.hierarchical_text_chunker import HierarchicalTextChunker
from backend.app.helpers.jina_fetcher import DefaultJinaFetcher
from backend.app.helpers.jina_eval_dataset_writer import JsonlJinaEvalDatasetWriter
from backend.tests.fixtures.factories import make_planner_output


class FakeJinaReaderClient(JinaReaderClient):
    def __init__(self, documents_by_url: dict[str, JinaReaderDocument | Exception]) -> None:
        self._documents_by_url = documents_by_url
        self.calls: list[str] = []

    def fetch_url(self, *, url: str) -> JinaReaderDocument:
        self.calls.append(url)
        result = self._documents_by_url.get(url) or self._documents_by_url[url.rstrip("/")]
        if isinstance(result, Exception):
            raise result
        return result


def test_default_jina_fetcher_chunks_successful_docs_and_marks_failures() -> None:
    fake_client = FakeJinaReaderClient(
        {
            "https://acmehealth.com/about": JinaReaderDocument(
                url="https://acmehealth.com/about",
                title="Acme Health",
                text=(
                    "Title: Acme Health\n\n"
                    "# About\n"
                    "Acme Health builds clinical AI.\n\n"
                    "# Team\n"
                    "Founded in Boston.\n\n"
                    "# Product\n"
                    "Supports hospital workflows."
                ),
            ),
            "https://broken.example.com": RuntimeError("upstream timeout"),
        }
    )
    fetcher = DefaultJinaFetcher(
        runtime_config=JinaFetcherRuntimeConfig(
            mode="jina",
            jina_api_key=None,
            reader_base_url="https://r.jina.ai",
            timeout_seconds=30.0,
            max_chunks_per_doc=2,
            max_chars_per_chunk=80,
            min_chars_per_chunk=20,
        ),
        jina_reader_client=fake_client,
    )

    output = fetcher.run(
        assessor_output=AssessorOutput(
            pass_type=AssessorPass.JINA_SELECTION,
            assessed_sources=[],
            verification_gaps=[],
            selected_jina_urls=[
                HttpUrl("https://acmehealth.com/about"),
                HttpUrl("https://broken.example.com"),
            ],
        ),
        remaining_fetch_budget=2,
    )

    assert len(output.url_sources) == 2
    assert output.url_sources[0].source_id == "jina:https://acmehealth.com/about"
    assert output.url_sources[0].title == "Acme Health"
    assert [chunk.text for chunk in output.url_sources[0].chunks] == [
        "Title: Acme Health\n\n# About\nAcme Health builds clinical AI.",
        "# Team\nFounded in Boston.\n\n# Product\nSupports hospital workflows.",
    ]
    assert output.url_sources[0].chunks[0].source_id == "jina:https://acmehealth.com/about"
    assert output.url_sources[0].chunks[0].chunk_id == "jina:https://acmehealth.com/about#0"
    assert output.url_sources[1].metadata == {
        "fetch_succeeded": False,
        "error_message": "upstream timeout",
    }


def test_hierarchical_chunker_avoids_tiny_tail_chunks_for_single_large_section() -> None:
    chunks = HierarchicalTextChunker(
        target_chunk_chars=100,
        max_chunks=10,
    ).chunk(
        text="alpha " * 40,
        source_id="jina:https://example.com/page",
    )

    assert len(chunks) == 3
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert len(chunks[-1].text) >= 20
    assert chunks[0].source_id == "jina:https://example.com/page"


def test_default_jina_fetcher_writes_deduped_eval_rows_when_query_bundle_is_provided(
    tmp_path: Path,
) -> None:
    dataset_path = tmp_path / "jina_eval.jsonl"
    fake_client = FakeJinaReaderClient(
        {
            "https://acmehealth.com/about": JinaReaderDocument(
                url="https://acmehealth.com/about",
                title="Acme Health",
                text=(
                    "# About\n"
                    "Acme Health builds clinical AI systems for hospitals.\n\n"
                    "# Product\n"
                    "Supports care-team workflows."
                ),
            ),
        }
    )
    fetcher = DefaultJinaFetcher(
        runtime_config=JinaFetcherRuntimeConfig(
            mode="jina",
            jina_api_key=None,
            reader_base_url="https://r.jina.ai",
            timeout_seconds=30.0,
            max_chunks_per_doc=4,
            max_chars_per_chunk=120,
            min_chars_per_chunk=20,
        ),
        jina_reader_client=fake_client,
        eval_dataset_writer=JsonlJinaEvalDatasetWriter(dataset_path=dataset_path),
    )
    planner_output = make_planner_output(
        base_query="AI startups in healthcare",
        normalized_query="AI startups in healthcare",
        initial_query_rewrites=["clinical AI startups", "hospital workflow automation startups"],
    )
    assessor_output = AssessorOutput(
        pass_type=AssessorPass.JINA_SELECTION,
        assessed_sources=[],
        verification_gaps=[],
        selected_jina_urls=[HttpUrl("https://acmehealth.com/about")],
    )

    fetcher.run(
        assessor_output=assessor_output,
        remaining_fetch_budget=1,
        request_query="find healthcare AI startups",
        planner_output=planner_output,
    )
    fetcher.run(
        assessor_output=assessor_output,
        remaining_fetch_budget=1,
        request_query="find healthcare AI startups",
        planner_output=planner_output,
    )

    records = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines()]

    assert len(records) == 1
    assert records[0] == {
        "request_query": "find healthcare AI startups",
        "normalized_query": "AI startups in healthcare",
        "base_query": "AI startups in healthcare",
        "query_rewrites": ["clinical AI startups", "hospital workflow automation startups"],
        "query_variants": [
            "AI startups in healthcare",
            "clinical AI startups",
            "hospital workflow automation startups",
        ],
        "source_url": "https://acmehealth.com/about",
        "source_title": "Acme Health",
        "chunk_id": "jina:https://acmehealth.com/about#0",
        "chunk_text": "# About\nAcme Health builds clinical AI systems for hospitals.\n\n# Product\nSupports care-team workflows.",
        "origin": "jina",
        "relevance": None,
        "judge_model": None,
        "label_reason": None,
    }
