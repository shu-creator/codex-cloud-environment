"""Evidence quote candidate extraction from messagelist pages."""
from __future__ import annotations

import re

_QUOTE_MAX_LEN = 30
_WHO_ID_LINE_RE = re.compile(r"(?:\d{10}-\d{3}|CUST-\d{3,4})")
_QUOTE_KEYWORDS = ("特記事項", "要望", "確認")
_DATE_RE = re.compile(r"\b\d{2}-\d{2}-\d{2}\b")
_TIME_RE = re.compile(r"\b\d{2}:\d{2}:\d{2}\b")
_NAME_SPACED_RE = re.compile(r"\bN\s*A\s*M\s*E\b", re.IGNORECASE)


def find_phrase_page(phrase: str, pages: list[tuple[int, str]]) -> int | None:
    """Return page number containing *phrase*, or ``None``."""
    for page_no, text in pages:
        if phrase in text:
            return page_no
    return None


def _is_header_line(text: str) -> bool:
    if _DATE_RE.search(text) or _TIME_RE.search(text):
        return True
    upper = text.upper()
    if "NO" in upper and "NAME" in upper:
        return True
    if _NAME_SPACED_RE.search(upper):
        return True
    return False


def _slice_quote(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    if len(stripped) <= _QUOTE_MAX_LEN:
        return stripped
    return stripped[:_QUOTE_MAX_LEN]


def _page_lines(text: str) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        lines.append((raw, stripped))
    return lines


def _add_unique_line(bucket: list[str], line: str) -> None:
    if line and line not in bucket:
        bucket.append(line)


def _collect_priority_lines(
    non_header: list[tuple[str, str]],
) -> tuple[list[str], list[str], list[str]]:
    who_lines: list[str] = []
    next_lines: list[str] = []
    keyword_lines: list[str] = []
    for idx, (_, stripped) in enumerate(non_header):
        if _WHO_ID_LINE_RE.search(stripped):
            _add_unique_line(who_lines, stripped)
            if idx + 1 < len(non_header):
                next_stripped = non_header[idx + 1][1]
                if next_stripped and not _is_header_line(next_stripped):
                    _add_unique_line(next_lines, next_stripped)
            continue
        if any(keyword in stripped for keyword in _QUOTE_KEYWORDS):
            _add_unique_line(keyword_lines, stripped)
    return who_lines, next_lines, keyword_lines


def _collect_other_lines(
    generic: list[tuple[str, str]], skip_lines: set[str],
) -> list[str]:
    other_lines: list[str] = []
    for _, stripped in generic:
        if stripped in skip_lines:
            continue
        _add_unique_line(other_lines, stripped)
    return other_lines


def _candidate_lines(text: str) -> list[str]:
    raw_lines = _page_lines(text)
    if not raw_lines:
        return []
    non_header = [(raw, stripped) for raw, stripped in raw_lines if not _is_header_line(stripped)]
    if not non_header:
        return []
    generic = non_header[2:] if len(non_header) > 2 else non_header

    who_lines, next_lines, keyword_lines = _collect_priority_lines(non_header)
    skip_lines = set(who_lines) | set(next_lines) | set(keyword_lines)
    other_lines = _collect_other_lines(generic, skip_lines)
    return who_lines + next_lines + keyword_lines + other_lines


def select_quote_candidates(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Select evidence quote candidates from messagelist pages.

    Returns list of ``(page_no, quote)`` tuples, prioritising lines
    containing customer IDs, lines following them, and keyword lines.
    """
    candidates: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for page_no, text in pages:
        for line in _candidate_lines(text):
            quote = _slice_quote(line)
            if not quote:
                continue
            if quote not in text:
                continue
            key = (page_no, quote)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(key)
    return candidates
