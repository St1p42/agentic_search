from __future__ import annotations

"""Deterministic cleanup for Brave LLM Context passage text."""

import json
import re
from html import unescape


IMAGE_MARKDOWN_PATTERN = re.compile(r"\*\[Image(?:[^\]]*)\]\*", re.IGNORECASE)
TABLE_SCAFFOLDING_PATTERN = re.compile(r"^\|?\s*(?:[-:]+\s*\|\s*)+[-:]*\|?$|^\|$")
BOILERPLATE_LINE_PATTERN = re.compile(
    r"^(?:"
    r"read more(?:\s+below)?(?:\.\.\.)?|"
    r"read full review|"
    r"learn more|"
    r"show pros\s*&\s*cons|"
    r"hide pros\s*&\s*cons|"
    r"show \d+ more show top \d+ only|"
    r"jump to(?::| see more details)?|"
    r"skip to main content|"
    r"become a techradar insider(?: now)?|"
    r"join our community|"
    r"join now|"
    r"sign up(?: for breaking news, reviews, opinion, top tech deals, and more\.)?|"
    r"commenting access|"
    r"member badges|"
    r"exclusive deals|"
    r"find out about our magazine|"
    r"find out more|"
    r"my account|"
    r"earn your first badge|"
    r"keep earning badges|"
    r"latest in phones|"
    r"latest in computing|"
    r"start reading|"
    r"your membership perks|"
    r"explore now|"
    r"member exclusives|"
    r"member rewards|"
    r"see rewards|"
    r"sign out|"
    r"share|"
    r"follow us|"
    r"newsletter|"
    r"you are now subscribed|"
    r"your newsletter sign-up was successful|"
    r"join the club|"
    r"explore|"
    r"terms\s*&\s*conditions|"
    r"privacy policy|"
    r"check(?: on amazon)?|"
    r"view deal"
    r")$",
    re.IGNORECASE,
)


def clean_brave_context_passage_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            cleaned_lines.append("")
            continue
        normalized_line = _normalize_passage_line(stripped_line)
        if IMAGE_MARKDOWN_PATTERN.search(stripped_line):
            continue
        if TABLE_SCAFFOLDING_PATTERN.fullmatch(stripped_line):
            continue
        if BOILERPLATE_LINE_PATTERN.fullmatch(normalized_line):
            continue
        if _is_json_blob(stripped_line):
            continue
        cleaned_lines.append(stripped_line)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned_lines)).strip()


def _is_json_blob(text: str) -> bool:
    if not (
        (text.startswith("{") and text.endswith("}"))
        or (text.startswith("[") and text.endswith("]"))
    ):
        return False

    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return True


def _normalize_passage_line(text: str) -> str:
    normalized = unescape(text).strip()
    normalized = normalized.strip("|").strip()
    normalized = re.sub(r"^[#>*_\-\s]+", "", normalized)
    normalized = re.sub(r"[>*_\-\s]+$", "", normalized)
    return normalized.strip()
