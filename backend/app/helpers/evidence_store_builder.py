from __future__ import annotations

"""Evidence-store builder helper owned by the orchestrator."""

from typing import Protocol

from backend.app.contracts import (
    AssessorOutput,
    BraveContextOutput,
    EvidenceStore,
    ExtractorLightOutput,
    JinaFetcherOutput,
)


class EvidenceStoreBuilder(Protocol):
    def run(
        self,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        jina_fetcher_output: JinaFetcherOutput | None = None,
        existing_store: EvidenceStore | None = None,
    ) -> EvidenceStore:
        """Build or merge the entity-centric evidence store."""


class PlaceholderEvidenceStoreBuilder:
    def run(
        self,
        brave_context_output: BraveContextOutput,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        jina_fetcher_output: JinaFetcherOutput | None = None,
        existing_store: EvidenceStore | None = None,
    ) -> EvidenceStore:
        _ = brave_context_output
        _ = extractor_light_output
        _ = assessor_output
        _ = jina_fetcher_output
        return existing_store or EvidenceStore(chunks_by_entity={})
