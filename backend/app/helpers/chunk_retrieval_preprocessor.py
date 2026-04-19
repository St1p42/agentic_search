from __future__ import annotations

"""Chunk/query retrieval preprocessing for BM25-style scoring."""

import re
import unicodedata
from typing import Protocol

from bm25s.tokenization import STOPWORDS_EN
from krovetzstemmer import Stemmer


DEFAULT_TOKEN_PATTERN = re.compile(r"(?u)\b\w+\b")


class ChunkRetrievalPreprocessor(Protocol):
    def preprocess_text(self, text: str) -> list[str]:
        """Return normalized retrieval tokens for one text item."""

    def preprocess_texts(self, texts: list[str]) -> list[list[str]]:
        """Return normalized retrieval tokens for multiple text items."""


class DefaultChunkRetrievalPreprocessor:
    def __init__(
        self,
        *,
        stemmer: Stemmer | None = None,
        stopwords: set[str] | None = None,
        token_pattern: re.Pattern[str] | None = None,
    ) -> None:
        self._stemmer = stemmer or Stemmer()
        self._stopwords = stopwords or set(STOPWORDS_EN)
        self._token_pattern = token_pattern or DEFAULT_TOKEN_PATTERN

    def preprocess_text(self, text: str) -> list[str]:
        normalized_text = self.normalize_text(text)
        tokens = self.tokenize(normalized_text)
        lowered_tokens = self.lowercase(tokens)
        filtered_tokens = self.filter_stopwords(lowered_tokens)
        return self.stem(filtered_tokens)

    def preprocess_texts(self, texts: list[str]) -> list[list[str]]:
        return [self.preprocess_text(text) for text in texts]

    def normalize_text(self, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
        normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
        normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
        return normalized

    def tokenize(self, text: str) -> list[str]:
        return self._token_pattern.findall(text)

    def lowercase(self, tokens: list[str]) -> list[str]:
        return [token.casefold() for token in tokens]

    def filter_stopwords(self, tokens: list[str]) -> list[str]:
        return [token for token in tokens if token not in self._stopwords]

    def stem(self, tokens: list[str]) -> list[str]:
        return [self._stemmer.stem(token) for token in tokens]
