from __future__ import annotations

from pydantic import HttpUrl

from backend.app.api_clients import JinaReaderClient, JinaReaderDocument
from backend.app.config import JinaFetcherRuntimeConfig
from backend.app.contracts import AssessorOutput, AssessorPass
from backend.app.helpers.jina_fetcher import DefaultJinaFetcher, chunk_document_text


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

    assert len(output.fetched_documents) == 2
    assert output.fetched_documents[0].fetch_succeeded is True
    assert output.fetched_documents[0].title == "Acme Health"
    assert [chunk.text for chunk in output.fetched_documents[0].chunks] == [
        "Title: Acme Health\n\n# About\nAcme Health builds clinical AI.",
        "# Team\nFounded in Boston.\n\n# Product\nSupports hospital workflows.",
    ]
    assert output.fetched_documents[0].chunks[0].source_id == "jina:https://acmehealth.com/about"
    assert output.fetched_documents[0].chunks[0].chunk_id == "jina:https://acmehealth.com/about#0"
    assert output.url_sources[0].source_id == "jina:https://acmehealth.com/about"
    assert output.url_sources[0].title == "Acme Health"
    assert [chunk.text for chunk in output.url_sources[0].chunks] == [
        "Title: Acme Health\n\n# About\nAcme Health builds clinical AI.",
        "# Team\nFounded in Boston.\n\n# Product\nSupports hospital workflows.",
    ]
    assert output.url_sources[1].metadata == {
        "fetch_succeeded": False,
        "error_message": "upstream timeout",
    }
    assert output.fetched_documents[1].fetch_succeeded is False
    assert output.fetched_documents[1].error_message == "upstream timeout"


def test_chunk_document_text_avoids_tiny_tail_chunks_for_single_large_section() -> None:
    chunks = chunk_document_text(
        "alpha " * 40,
        source_id="jina:https://example.com/page",
        max_chunks=10,
        max_chars_per_chunk=100,
    )

    assert len(chunks) == 3
    assert all(len(chunk.text) <= 100 for chunk in chunks)
    assert len(chunks[-1].text) >= 20
    assert chunks[0].source_id == "jina:https://example.com/page"
