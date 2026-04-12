from __future__ import annotations

import re
import unicodedata

from pydantic import HttpUrl

from backend.app.contracts import PlannerOutput


GENERIC_CATEGORY_PHRASES = {
    "ai startups",
    "healthcare ai startups",
    "healthcare companies",
    "top restaurants",
    "best phones",
    "open source tools",
}
GENERIC_DESCRIPTOR_TOKENS = {
    "ai",
    "best",
    "clinical",
    "companies",
    "company",
    "healthcare",
    "leading",
    "most",
    "open",
    "phones",
    "popular",
    "recommended",
    "restaurants",
    "source",
    "startups",
    "tools",
    "top",
}
GENERIC_CATEGORY_HEADS = {
    "apps",
    "companies",
    "company",
    "datasets",
    "phones",
    "platforms",
    "products",
    "restaurants",
    "services",
    "solutions",
    "startups",
    "tools",
}
GENERIC_LEADING_TERMS = {"best", "leading", "most", "popular", "recommended", "top"}
BOILERPLATE_LABELS = {
    "about",
    "about us",
    "contact",
    "overview",
    "portfolio",
    "pricing",
    "products",
    "services",
    "solutions",
    "team",
}
WEAK_GENERIC_SINGLE_TOKENS = {
    "app",
    "company",
    "directory",
    "guide",
    "marketplace",
    "overview",
    "platform",
    "portfolio",
    "restaurant",
    "service",
    "software",
    "solution",
    "startup",
    "team",
    "tool",
}


class EntityNameFilter:
    def filter(
        self,
        *,
        planner_output: PlannerOutput,
        candidate_names: list[str],
        name_to_source_urls: dict[str, list[HttpUrl]],
        mention_counts: dict[str, int],
    ) -> tuple[list[str], dict[str, list[HttpUrl]], dict[str, int]]:
        kept_candidate_names: list[str] = []
        kept_name_to_source_urls: dict[str, list[HttpUrl]] = {}
        kept_mention_counts: dict[str, int] = {}

        for candidate_name in candidate_names:
            source_urls = name_to_source_urls.get(candidate_name, [])
            mention_count = mention_counts.get(candidate_name, 0)
            if self._should_drop(
                planner_output=planner_output,
                candidate_name=candidate_name,
                source_urls=source_urls,
                mention_count=mention_count,
            ):
                continue
            kept_candidate_names.append(candidate_name)
            kept_name_to_source_urls[candidate_name] = source_urls
            kept_mention_counts[candidate_name] = mention_count

        return kept_candidate_names, kept_name_to_source_urls, kept_mention_counts

    def _should_drop(
        self,
        *,
        planner_output: PlannerOutput,
        candidate_name: str,
        source_urls: list[HttpUrl],
        mention_count: int,
    ) -> bool:
        _ = planner_output
        normalized_name = _normalize_phrase(candidate_name)
        if not source_urls:
            return True
        if mention_count <= 0:
            return True
        if _is_generic_category_phrase(normalized_name):
            return True
        if normalized_name in BOILERPLATE_LABELS:
            return True
        if _is_malformed_compound(candidate_name):
            return True
        if _is_weak_generic_single_token(normalized_name):
            return True
        return False


def _normalize_phrase(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.casefold())
    normalized = normalized.replace("’", "'").replace("‘", "'").replace("`", "'")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" \t\n\r\"'“”‘’.,;:!?()[]{}<>")


def _is_generic_category_phrase(normalized_name: str) -> bool:
    if not normalized_name:
        return False
    if normalized_name in GENERIC_CATEGORY_PHRASES:
        return True

    tokens = normalized_name.split()
    if not tokens:
        return False
    if tokens[0] in GENERIC_LEADING_TERMS and tokens[-1] in GENERIC_CATEGORY_HEADS:
        return True
    if tokens[-1] in GENERIC_CATEGORY_HEADS and all(token in GENERIC_DESCRIPTOR_TOKENS for token in tokens):
        return True
    return False


def _is_malformed_compound(candidate_name: str) -> bool:
    normalized_name = _normalize_phrase(candidate_name)
    if "/" in normalized_name:
        return True
    if " vs " in normalized_name:
        return True
    if " and/or " in normalized_name:
        return True
    return False


def _is_weak_generic_single_token(normalized_name: str) -> bool:
    tokens = normalized_name.split()
    return len(tokens) == 1 and tokens[0] in WEAK_GENERIC_SINGLE_TOKENS
