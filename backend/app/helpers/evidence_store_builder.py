from __future__ import annotations

"""Evidence-store builder helper owned by the orchestrator."""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol

from pydantic import HttpUrl

from backend.app.contracts import (
    AssessedSource,
    AssessorOutput,
    ChunkRankingOutput,
    EvidenceChunk,
    EvidenceOrigin,
    EvidenceStore,
    ExtractorLightOutput,
    OfficialityLevel,
    RankedChunk,
    ChunkScore,
    RetrievedSourcesOutput,
    SourceQuality,
    SourceRole,
    UrlSource,
)


MAX_ENTITY_WINDOW_CHARS = 1200
MIN_ENTITY_WINDOW_CHARS = 50
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+|\n+")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class BaseChunkMetadata:
    source_url: HttpUrl
    source_title: str
    source_role: SourceRole
    source_quality: SourceQuality
    officiality: OfficialityLevel
    origin: EvidenceOrigin
    aspect_coverage: list[str]


@dataclass(frozen=True)
class SourceRecord:
    source_url: str
    text: str
    metadata: BaseChunkMetadata


@dataclass(frozen=True)
class SentenceUnit:
    text: str
    paragraph_index: int
    normalized_text: str
    token_set: frozenset[str]


class EvidenceStoreBuilder(Protocol):
    def run(
        self,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        existing_store: EvidenceStore | None = None,
        chunk_ranking_output: ChunkRankingOutput | None = None,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> EvidenceStore:
        """Build or merge the entity-centric evidence store."""


class DefaultEvidenceStoreBuilder:
    def run(
        self,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        existing_store: EvidenceStore | None = None,
        chunk_ranking_output: ChunkRankingOutput | None = None,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> EvidenceStore:
        chunk_ranking_output = chunk_ranking_output or _chunk_ranking_output_from_retrieved_sources(
            brave_context_output or RetrievedSourcesOutput()
        )
        chunks_by_entity = _clone_existing_chunks(existing_store)
        seen_keys_by_entity = _index_existing_chunk_keys(chunks_by_entity)
        assessed_sources_by_url = _assessed_sources_by_url(assessor_output)
        candidate_names = _candidate_names(extractor_light_output)
        candidate_matchers = _candidate_matchers(candidate_names)
        candidate_urls = _candidate_urls(extractor_light_output)
        stop_entities = _stop_entities(
            extractor_light_output=extractor_light_output,
            assessed_sources_by_url=assessed_sources_by_url,
        )
        source_records = _source_records(
            chunk_ranking_output=chunk_ranking_output,
            assessed_sources_by_url=assessed_sources_by_url,
        )

        for source_record in source_records:
            _attach_source_record(
                source_record=source_record,
                chunks_by_entity=chunks_by_entity,
                seen_keys_by_entity=seen_keys_by_entity,
                candidate_names=candidate_names,
                candidate_matchers=candidate_matchers,
                candidate_urls=candidate_urls,
                stop_entities=stop_entities,
            )

        return EvidenceStore(
            chunks_by_entity=chunks_by_entity,
            entity_scores=_entity_scores(chunks_by_entity),
        )


class PlaceholderEvidenceStoreBuilder:
    def run(
        self,
        extractor_light_output: ExtractorLightOutput,
        assessor_output: AssessorOutput,
        existing_store: EvidenceStore | None = None,
        chunk_ranking_output: ChunkRankingOutput | None = None,
        brave_context_output: RetrievedSourcesOutput | None = None,
    ) -> EvidenceStore:
        _ = chunk_ranking_output
        _ = brave_context_output
        _ = extractor_light_output
        _ = assessor_output
        return existing_store or EvidenceStore(chunks_by_entity={}, entity_scores={})


def build_evidence_store_builder() -> EvidenceStoreBuilder:
    return DefaultEvidenceStoreBuilder()


def _clone_existing_chunks(existing_store: EvidenceStore | None) -> dict[str, list[EvidenceChunk]]:
    if not existing_store:
        return {}
    return {
        entity_name: list(chunks)
        for entity_name, chunks in existing_store.chunks_by_entity.items()
    }


def _index_existing_chunk_keys(
    chunks_by_entity: dict[str, list[EvidenceChunk]],
) -> dict[str, set[tuple[str, str]]]:
    seen_keys_by_entity: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for entity_name, chunks in chunks_by_entity.items():
        seen_keys_by_entity[entity_name].update(_chunk_key(chunk) for chunk in chunks)
    return seen_keys_by_entity


def _assessed_sources_by_url(assessor_output: AssessorOutput) -> dict[str, AssessedSource]:
    return {
        str(assessed_source.result.url): assessed_source
        for assessed_source in assessor_output.assessed_sources
    }


def _candidate_names(extractor_light_output: ExtractorLightOutput) -> list[str]:
    return [name for name in extractor_light_output.candidate_names if name.strip()]


def _candidate_matchers(candidate_names: list[str]) -> dict[str, tuple[str, frozenset[str]]]:
    return {
        candidate_name: _candidate_matcher(candidate_name)
        for candidate_name in candidate_names
    }


def _candidate_urls(extractor_light_output: ExtractorLightOutput) -> dict[str, set[str]]:
    return {
        candidate_name: {str(url) for url in urls}
        for candidate_name, urls in extractor_light_output.name_to_source_urls.items()
    }


def _stop_entities(
    *,
    extractor_light_output: ExtractorLightOutput,
    assessed_sources_by_url: dict[str, AssessedSource],
) -> set[str]:
    stop_entities: set[str] = set()
    for candidate_name in extractor_light_output.candidate_names:
        mention_count = extractor_light_output.mention_counts.get(candidate_name, 0)
        if mention_count >= 2:
            stop_entities.add(candidate_name)
            continue
        source_urls = extractor_light_output.name_to_source_urls.get(candidate_name, [])
        if any(_is_non_low_source(assessed_sources_by_url.get(str(source_url))) for source_url in source_urls):
            stop_entities.add(candidate_name)
    return stop_entities


def _is_non_low_source(assessed_source: AssessedSource | None) -> bool:
    if assessed_source is None:
        return False
    return (
        not assessed_source.filtered_out
        and
        assessed_source.source_quality != SourceQuality.LOW
        and assessed_source.officiality != OfficialityLevel.LOW_QUALITY
    )


def _source_records(
    *,
    chunk_ranking_output: ChunkRankingOutput,
    assessed_sources_by_url: dict[str, AssessedSource],
) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    selected_chunk_ids = set(chunk_ranking_output.selected_chunk_ids)
    if not selected_chunk_ids:
        return records
    for url_source in chunk_ranking_output.url_sources:
        if url_source.metadata.get("fetch_succeeded") is False:
            continue
        assessed_source = assessed_sources_by_url.get(str(url_source.url))
        if assessed_source is not None and assessed_source.filtered_out:
            continue
        records.extend(
            _source_records_for_url_source(
                url_source=url_source,
                selected_chunk_ids=selected_chunk_ids,
                assessed_source=assessed_source,
            )
        )
    return records


def _source_records_for_url_source(
    *,
    url_source: UrlSource,
    selected_chunk_ids: set[str],
    assessed_source: AssessedSource | None,
) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for chunk in url_source.chunks:
        if chunk.chunk_id not in selected_chunk_ids:
            continue
        text = chunk.text.strip()
        if not text:
            continue
        records.append(
            SourceRecord(
                source_url=str(url_source.url),
                text=text,
                metadata=_base_chunk_metadata(
                    source_url=url_source.url,
                    source_title=url_source.title,
                    assessed_source=assessed_source,
                    origin=url_source.origin,
                ),
            )
        )
    return records


def _chunk_ranking_output_from_retrieved_sources(
    retrieved_sources_output: RetrievedSourcesOutput,
) -> ChunkRankingOutput:
    ranked_chunks: list[RankedChunk] = []
    selected_chunk_ids: list[str] = []
    rank = 1
    for url_source in retrieved_sources_output.url_sources:
        for chunk in url_source.chunks:
            ranked_chunks.append(
                RankedChunk(
                    source_id=url_source.source_id,
                    chunk_id=chunk.chunk_id,
                    rank=rank,
                    score=ChunkScore(final_score=0.0),
                )
            )
            selected_chunk_ids.append(chunk.chunk_id)
            rank += 1
    return ChunkRankingOutput(
        url_sources=retrieved_sources_output.url_sources,
        ranked_chunks=ranked_chunks,
        selected_chunk_ids=selected_chunk_ids,
    )


def _base_chunk_metadata(
    *,
    source_url: HttpUrl,
    source_title: str,
    assessed_source: AssessedSource | None,
    origin: EvidenceOrigin,
) -> BaseChunkMetadata:
    return BaseChunkMetadata(
        source_url=source_url,
        source_title=source_title,
        source_role=_source_role(assessed_source),
        source_quality=_source_quality(assessed_source),
        officiality=_officiality(assessed_source),
        origin=origin,
        aspect_coverage=_aspect_coverage(assessed_source),
    )


def _attach_source_record(
    *,
    source_record: SourceRecord,
    chunks_by_entity: dict[str, list[EvidenceChunk]],
    seen_keys_by_entity: dict[str, set[tuple[str, str]]],
    candidate_names: list[str],
    candidate_matchers: dict[str, tuple[str, frozenset[str]]],
    candidate_urls: dict[str, set[str]],
    stop_entities: set[str],
) -> None:
    primary_entities = _primary_entities(
        source_url=source_record.source_url,
        candidate_names=candidate_names,
        candidate_urls=candidate_urls,
    )
    sentences = _sentence_units(source_record.text)
    sentence_matches = _sentence_matches(
        sentences=sentences,
        candidate_matchers=candidate_matchers,
    )

    target_entities = primary_entities or _fallback_entities(
        sentence_matches=sentence_matches,
        candidate_names=candidate_names,
    )
    for entity_name in target_entities:
        windows = _entity_windows(
            entity_name=entity_name,
            sentences=sentences,
            sentence_matches=sentence_matches,
            stop_entities=stop_entities,
        )
        for window_text in windows:
            _append_chunk(
                chunks_by_entity=chunks_by_entity,
                seen_keys_by_entity=seen_keys_by_entity,
                entity_name=entity_name,
                chunk=_evidence_chunk(text=window_text, metadata=source_record.metadata),
            )


def _primary_entities(
    *,
    source_url: str,
    candidate_names: list[str],
    candidate_urls: dict[str, set[str]],
) -> list[str]:
    return [
        candidate_name
        for candidate_name in candidate_names
        if source_url in candidate_urls.get(candidate_name, set())
    ]


def _fallback_entities(
    *,
    sentence_matches: list[set[str]],
    candidate_names: list[str],
) -> list[str]:
    matched_names = set().union(*sentence_matches) if sentence_matches else set()
    return [candidate_name for candidate_name in candidate_names if candidate_name in matched_names]


def _sentence_units(text: str) -> list[SentenceUnit]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    sentence_units: list[SentenceUnit] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        raw_sentences = [segment.strip() for segment in SENTENCE_SPLIT_PATTERN.split(paragraph) if segment.strip()]
        if not raw_sentences:
            continue
        for raw_sentence in raw_sentences:
            normalized_text = _normalize_text(raw_sentence)
            sentence_units.append(
                SentenceUnit(
                    text=raw_sentence,
                    paragraph_index=paragraph_index,
                    normalized_text=normalized_text,
                    token_set=frozenset(_tokens(normalized_text)),
                )
            )
    return sentence_units


def _sentence_matches(
    *,
    sentences: list[SentenceUnit],
    candidate_matchers: dict[str, tuple[str, frozenset[str]]],
) -> list[set[str]]:
    matches: list[set[str]] = []
    for sentence in sentences:
        sentence_match_set: set[str] = set()
        for candidate_name, (normalized_name, token_set) in candidate_matchers.items():
            if token_set and not token_set.issubset(sentence.token_set):
                continue
            if normalized_name in sentence.normalized_text:
                sentence_match_set.add(candidate_name)
        matches.append(sentence_match_set)
    return matches


def _entity_windows(
    *,
    entity_name: str,
    sentences: list[SentenceUnit],
    sentence_matches: list[set[str]],
    stop_entities: set[str],
) -> list[str]:
    windows: list[str] = []
    seen_spans: set[tuple[int, int]] = set()
    for index, matched_entities in enumerate(sentence_matches):
        if entity_name not in matched_entities:
            continue
        if len(matched_entities) > 1:
            continue
        start, end = _expand_sentence_window(
            entity_name=entity_name,
            start_index=index,
            sentences=sentences,
            sentence_matches=sentence_matches,
            stop_entities=stop_entities,
        )
        span = (start, end)
        if span in seen_spans:
            continue
        window_text = " ".join(sentence.text for sentence in sentences[start : end + 1]).strip()
        if len(window_text) < MIN_ENTITY_WINDOW_CHARS:
            continue
        seen_spans.add(span)
        windows.append(window_text)
    return windows


def _expand_sentence_window(
    *,
    entity_name: str,
    start_index: int,
    sentences: list[SentenceUnit],
    sentence_matches: list[set[str]],
    stop_entities: set[str],
) -> tuple[int, int]:
    left = start_index
    right = start_index
    current_chars = len(sentences[start_index].text)
    left_active = True
    right_active = True

    while left_active or right_active:
        if left_active:
            next_left = left - 1
            if next_left < 0:
                left_active = False
            elif not _can_expand_to_sentence(
                entity_name=entity_name,
                current_index=left,
                next_index=next_left,
                current_chars=current_chars,
                sentences=sentences,
                sentence_matches=sentence_matches,
                stop_entities=stop_entities,
            ):
                left_active = False
            else:
                left = next_left
                current_chars += len(sentences[next_left].text) + 1

        if right_active:
            next_right = right + 1
            if next_right >= len(sentences):
                right_active = False
            elif not _can_expand_to_sentence(
                entity_name=entity_name,
                current_index=right,
                next_index=next_right,
                current_chars=current_chars,
                sentences=sentences,
                sentence_matches=sentence_matches,
                stop_entities=stop_entities,
            ):
                right_active = False
            else:
                right = next_right
                current_chars += len(sentences[next_right].text) + 1

    return left, right


def _can_expand_to_sentence(
    *,
    entity_name: str,
    current_index: int,
    next_index: int,
    current_chars: int,
    sentences: list[SentenceUnit],
    sentence_matches: list[set[str]],
    stop_entities: set[str],
) -> bool:
    if sentences[next_index].paragraph_index != sentences[current_index].paragraph_index:
        return False
    if current_chars + len(sentences[next_index].text) + 1 > MAX_ENTITY_WINDOW_CHARS:
        return False
    next_sentence_entities = sentence_matches[next_index]
    if any(other_entity != entity_name and other_entity in stop_entities for other_entity in next_sentence_entities):
        return False
    return True


def _evidence_chunk(*, text: str, metadata: BaseChunkMetadata) -> EvidenceChunk:
    return EvidenceChunk(
        text=text,
        source_url=metadata.source_url,
        source_title=metadata.source_title,
        source_role=metadata.source_role,
        source_quality=metadata.source_quality,
        officiality=metadata.officiality,
        origin=metadata.origin,
        aspect_coverage=list(metadata.aspect_coverage),
    )


def _append_chunk(
    *,
    chunks_by_entity: dict[str, list[EvidenceChunk]],
    seen_keys_by_entity: dict[str, set[tuple[str, str]]],
    entity_name: str,
    chunk: EvidenceChunk,
) -> None:
    chunk_key = _chunk_key(chunk)
    if chunk_key in seen_keys_by_entity[entity_name]:
        return
    chunks_by_entity.setdefault(entity_name, []).append(chunk)
    seen_keys_by_entity[entity_name].add(chunk_key)


def _entity_scores(chunks_by_entity: dict[str, list[EvidenceChunk]]) -> dict[str, float]:
    return {
        entity_name: _entity_score(chunks)
        for entity_name, chunks in chunks_by_entity.items()
    }


def _entity_score(chunks: list[EvidenceChunk]) -> float:
    best_score_by_url: dict[str, float] = {}
    for chunk in chunks:
        source_url = str(chunk.source_url)
        source_score = _source_score(chunk)
        previous_score = best_score_by_url.get(source_url, 0.0)
        if source_score > previous_score:
            best_score_by_url[source_url] = source_score
    return sum(best_score_by_url.values())


def _source_score(chunk: EvidenceChunk) -> float:
    if chunk.source_quality == SourceQuality.HIGH and chunk.officiality != OfficialityLevel.LOW_QUALITY:
        return 1.0
    if chunk.source_quality == SourceQuality.MEDIUM and chunk.officiality != OfficialityLevel.LOW_QUALITY:
        return 0.5
    return 0.0


def _chunk_key(chunk: EvidenceChunk) -> tuple[str, str]:
    return str(chunk.source_url), chunk.text


def _candidate_matcher(candidate_name: str) -> tuple[str, frozenset[str]]:
    normalized_name = _normalize_text(candidate_name)
    return normalized_name, frozenset(_tokens(normalized_name))


def _normalize_text(text: str) -> str:
    return " ".join(_tokens(text))


def _tokens(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _source_title(
    *,
    source_url: HttpUrl,
    metadata: dict[str, str | int | float | bool | None],
    assessed_source: AssessedSource | None,
) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    if assessed_source is not None:
        return assessed_source.result.title
    return str(source_url)


def _source_role(assessed_source: AssessedSource | None) -> SourceRole:
    if assessed_source is None:
        return SourceRole.DISCOVERY
    return assessed_source.source_role


def _source_quality(assessed_source: AssessedSource | None) -> SourceQuality:
    if assessed_source is None:
        return SourceQuality.MEDIUM
    return assessed_source.source_quality


def _officiality(assessed_source: AssessedSource | None) -> OfficialityLevel:
    if assessed_source is None:
        return OfficialityLevel.THIRD_PARTY
    return assessed_source.officiality


def _aspect_coverage(assessed_source: AssessedSource | None) -> list[str]:
    if assessed_source is None:
        return []
    return list(assessed_source.estimated_aspect_coverage)
