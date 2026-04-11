from __future__ import annotations

import re
from urllib.parse import urlparse


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")
OFFICIAL_PATH_MARKERS = ("/about", "/company", "/contact", "/team", "/product", "/platform")
THIRD_PARTY_PATTERNS = (
    "best",
    "top",
    "review",
    "reviews",
    "alternatives",
    "compare",
    "comparison",
    "directory",
    "list",
    "roundup",
    "news",
)
LOW_QUALITY_HOST_MARKERS = (
    "reddit.com",
    "quora.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "pinterest.com",
)
GENERIC_SUBDOMAIN_MARKERS = {"www", "app", "blog", "docs", "help", "support"}


def normalize_compact(text: str) -> str:
    return NON_ALNUM_PATTERN.sub("", text.lower())


def tokenize(text: str) -> set[str]:
    return {token for token in TOKEN_PATTERN.findall(text.lower()) if len(token) > 1}


def hostname(url: str) -> str:
    return urlparse(url).netloc.lower()


def hostname_core(url: str) -> str:
    host = hostname(url)
    labels = [label for label in host.split(".") if label and label not in GENERIC_SUBDOMAIN_MARKERS]
    if len(labels) >= 2:
        labels = labels[:-1]
    return normalize_compact("".join(labels))


def path(url: str) -> str:
    return urlparse(url).path.lower()


def path_segment_count(url: str) -> int:
    return len([segment for segment in path(url).split("/") if segment])


def has_official_path(url: str) -> bool:
    lowered_path = path(url)
    return any(marker in lowered_path for marker in OFFICIAL_PATH_MARKERS)


def has_low_quality_host_marker(url: str) -> bool:
    host = hostname(url)
    return any(marker in host for marker in LOW_QUALITY_HOST_MARKERS)


def has_third_party_pattern(*values: str) -> bool:
    lowered = " ".join(values).lower()
    return any(pattern in lowered for pattern in THIRD_PARTY_PATTERNS)
