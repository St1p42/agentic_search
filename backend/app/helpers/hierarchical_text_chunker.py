from __future__ import annotations

"""Hierarchical plaintext chunker for request-scoped retrieval."""

import re
from dataclasses import dataclass

from backend.app.contracts import RetrievedChunk


MAJOR_HEADING_PATTERN = re.compile(r"(?m)(?=^#{1,6}\s+)")
MAJOR_GAP_PATTERN = re.compile(r"\n{3,}")
PARAGRAPH_BREAK_PATTERN = re.compile(r"\n{2,}")
SINGLE_NEWLINE_PATTERN = re.compile(r"\n")
SENTENCE_BREAK_PATTERN = re.compile(r"(?<=[.!?])(?:\s+|$)")
WHITESPACE_PATTERN = re.compile(r"\s+")

MIN_CHUNK_CHARS_FRACTION = 0.35


@dataclass(frozen=True)
class LeafSpan:
    start: int
    end: int
    split_level: int


class HierarchicalTextChunker:
    def __init__(
        self,
        *,
        target_chunk_chars: int,
        min_chunk_chars: int | None = None,
        max_chunks: int | None = None,
    ) -> None:
        if target_chunk_chars <= 0:
            raise ValueError("target_chunk_chars must be positive")
        self._target_chunk_chars = target_chunk_chars
        self._min_chunk_chars = min_chunk_chars or max(1, int(target_chunk_chars * MIN_CHUNK_CHARS_FRACTION))
        self._max_chunks = max_chunks

    def chunk(
        self,
        *,
        text: str,
        source_id: str,
    ) -> list[RetrievedChunk]:
        normalized_text = _normalize_text(text)
        if not normalized_text:
            return []

        leaf_spans = self._collect_leaves(normalized_text, 0, len(normalized_text), level=0)
        merged_spans = self._merge_small_leaves(normalized_text, leaf_spans)
        bounded_spans = self._enforce_max_chunks(normalized_text, merged_spans)
        return [
            RetrievedChunk(
                chunk_id=f"{source_id}#{index}",
                source_id=source_id,
                text=normalized_text[span.start : span.end].strip(),
                sequence_index=index,
            )
            for index, span in enumerate(bounded_spans)
            if normalized_text[span.start : span.end].strip()
        ]

    def _collect_leaves(
        self,
        text: str,
        start: int,
        end: int,
        *,
        level: int,
    ) -> list[LeafSpan]:
        span_text = text[start:end]
        if len(span_text.strip()) <= self._target_chunk_chars:
            return [LeafSpan(start=start, end=end, split_level=level)]

        boundaries = self._boundaries_for_level(text, start, end, level)
        if not boundaries:
            return self._collect_with_next_level_or_whitespace_fallback(text, start, end, level)

        spans = _spans_from_boundaries(start, end, boundaries)
        if len(spans) <= 1:
            return self._collect_with_next_level_or_whitespace_fallback(text, start, end, level)

        leaves: list[LeafSpan] = []
        for child_start, child_end in spans:
            leaves.extend(self._collect_leaves(text, child_start, child_end, level=level + 1))
        return leaves

    def _collect_with_next_level_or_whitespace_fallback(
        self,
        text: str,
        start: int,
        end: int,
        level: int,
    ) -> list[LeafSpan]:
        if level < 4:
            return self._collect_leaves(text, start, end, level=level + 1)

        midpoint = _best_whitespace_boundary(text, start, end, self._target_chunk_chars)
        if midpoint is None or midpoint <= start or midpoint >= end:
            return [LeafSpan(start=start, end=end, split_level=level)]
        return [
            *self._collect_leaves(text, start, midpoint, level=level + 1),
            *self._collect_leaves(text, midpoint, end, level=level + 1),
        ]

    def _boundaries_for_level(
        self,
        text: str,
        start: int,
        end: int,
        level: int,
    ) -> list[int]:
        span_text = text[start:end]
        if level == 0:
            return _major_boundaries(span_text, start)
        if level == 1:
            return _pattern_boundaries(PARAGRAPH_BREAK_PATTERN, span_text, start)
        if level == 2:
            heuristic_boundaries = _indented_line_boundaries(span_text, start)
            if heuristic_boundaries:
                return heuristic_boundaries
            return _pattern_boundaries(SINGLE_NEWLINE_PATTERN, span_text, start)
        if level == 3:
            return _pattern_boundaries(SENTENCE_BREAK_PATTERN, span_text, start)
        if level == 4:
            boundary = _best_whitespace_boundary(text, start, end, self._target_chunk_chars)
            return [boundary] if boundary is not None else []
        return []

    def _merge_small_leaves(self, text: str, leaf_spans: list[LeafSpan]) -> list[LeafSpan]:
        spans = list(leaf_spans)
        if len(spans) <= 1:
            return spans

        index = 0
        while index < len(spans):
            current = spans[index]
            current_size = len(text[current.start : current.end].strip())
            if current_size >= self._min_chunk_chars or len(spans) == 1:
                index += 1
                continue

            neighbor_index = _shortest_immediate_neighbor_index(text, spans, index)
            if neighbor_index is None:
                index += 1
                continue

            merged_index = min(index, neighbor_index)
            spans[merged_index] = LeafSpan(
                start=min(current.start, spans[neighbor_index].start),
                end=max(current.end, spans[neighbor_index].end),
                split_level=min(current.split_level, spans[neighbor_index].split_level),
            )
            del spans[max(index, neighbor_index)]
            index = max(0, merged_index - 1)

        return spans

    def _enforce_max_chunks(self, text: str, leaf_spans: list[LeafSpan]) -> list[LeafSpan]:
        if self._max_chunks is None or self._max_chunks <= 0:
            return leaf_spans

        spans = list(leaf_spans)
        while len(spans) > self._max_chunks and len(spans) > 1:
            merge_at = _smallest_adjacent_pair_index(text, spans)
            spans[merge_at] = LeafSpan(
                start=spans[merge_at].start,
                end=spans[merge_at + 1].end,
                split_level=min(spans[merge_at].split_level, spans[merge_at + 1].split_level),
            )
            del spans[merge_at + 1]
        return spans


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?m)[ \t]+$", "", normalized)
    normalized = normalized.strip()
    return normalized


def _major_boundaries(span_text: str, start_offset: int) -> list[int]:
    boundaries = _pattern_starts(MAJOR_HEADING_PATTERN, span_text, start_offset)
    boundaries.extend(_pattern_boundaries(MAJOR_GAP_PATTERN, span_text, start_offset))
    return sorted(set(boundary for boundary in boundaries if boundary is not None))


def _pattern_starts(pattern: re.Pattern[str], span_text: str, start_offset: int) -> list[int]:
    return [
        start_offset + match.start()
        for match in pattern.finditer(span_text)
        if match.start() > 0
    ]


def _pattern_boundaries(pattern: re.Pattern[str], span_text: str, start_offset: int) -> list[int]:
    return [
        start_offset + match.end()
        for match in pattern.finditer(span_text)
        if match.end() < len(span_text)
    ]


def _spans_from_boundaries(start: int, end: int, boundaries: list[int]) -> list[tuple[int, int]]:
    valid_boundaries = sorted(boundary for boundary in boundaries if start < boundary < end)
    if not valid_boundaries:
        return [(start, end)]

    spans: list[tuple[int, int]] = []
    cursor = start
    for boundary in valid_boundaries:
        if boundary <= cursor:
            continue
        spans.append((cursor, boundary))
        cursor = boundary
    if cursor < end:
        spans.append((cursor, end))
    return spans


def _best_whitespace_boundary(
    text: str,
    start: int,
    end: int,
    target_chunk_chars: int,
) -> int | None:
    if end - start <= target_chunk_chars:
        return None

    target_index = min(end - 1, start + target_chunk_chars)
    before_matches = [match.end() + start for match in WHITESPACE_PATTERN.finditer(text[start:target_index])]
    if before_matches:
        return before_matches[-1]

    after_matches = [match.start() + target_index for match in WHITESPACE_PATTERN.finditer(text[target_index:end])]
    if after_matches:
        return after_matches[0]
    return None


def _indented_line_boundaries(span_text: str, start_offset: int) -> list[int]:
    boundaries: list[int] = []
    for match in SINGLE_NEWLINE_PATTERN.finditer(span_text):
        left_text = span_text[: match.start()].rstrip()
        right_text = span_text[match.end() :]
        if not left_text or not right_text:
            continue
        if left_text[-1] not in ".!?":
            continue
        if right_text[:1] not in {" ", "\t"}:
            continue
        boundaries.append(start_offset + match.end())
    return boundaries


def _shortest_immediate_neighbor_index(
    text: str,
    spans: list[LeafSpan],
    index: int,
) -> int | None:
    candidates: list[tuple[int, int]] = []
    if index > 0:
        candidates.append((_span_size(text, spans[index - 1]), index - 1))
    if index + 1 < len(spans):
        candidates.append((_span_size(text, spans[index + 1]), index + 1))
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item[0], item[1]))[1]


def _smallest_adjacent_pair_index(text: str, spans: list[LeafSpan]) -> int:
    pair_scores = [
        (_span_size(text, spans[index]) + _span_size(text, spans[index + 1]), index)
        for index in range(len(spans) - 1)
    ]
    return min(pair_scores, key=lambda item: (item[0], item[1]))[1]


def _span_size(text: str, span: LeafSpan) -> int:
    return len(text[span.start : span.end].strip())
