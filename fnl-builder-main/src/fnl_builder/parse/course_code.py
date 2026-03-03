from __future__ import annotations

import re
import unicodedata

_COURSE_MARKER_RE = re.compile(r"コースNO\s*[：:]", re.IGNORECASE)
_COURSE_CANDIDATE_RE = re.compile(r"^\s*(?P<code>[A-Z]\s*Q\s*\d{4,6}|(?:[A-Z]\s*){1,2}\d{3}\s*[A-Z]{0,2})(?![A-Z0-9])")
_COURSE_STANDARD_RE = re.compile(r"^[A-Z]{1,2}\d{3}[A-Z]{0,2}$")
_COURSE_Q_SERIES_RE = re.compile(r"^[A-Z]Q\d{4,6}$")


def _normalize_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text).upper()


def _normalize_candidate(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _is_valid_course_code(value: str) -> bool:
    return bool(_COURSE_Q_SERIES_RE.fullmatch(value) or _COURSE_STANDARD_RE.fullmatch(value))


def find_course_codes(text: str, *, window: int = 80) -> list[str]:
    if not text:
        return []
    normalized = _normalize_text(text)
    found: list[str] = []
    for marker in _COURSE_MARKER_RE.finditer(normalized):
        segment = normalized[marker.end() : marker.end() + window]
        match = _COURSE_CANDIDATE_RE.match(segment)
        if not match:
            continue
        course_code = _normalize_candidate(match.group("code"))
        if not _is_valid_course_code(course_code):
            continue
        if course_code not in found:
            found.append(course_code)
    return found


def extract_course_code(text: str, *, window: int = 80) -> str | None:
    courses = find_course_codes(text, window=window)
    if len(courses) != 1:
        return None
    return courses[0]
