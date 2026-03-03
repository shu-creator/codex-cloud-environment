from __future__ import annotations

import re

from fnl_builder.shared.text import collapse_ws
from fnl_builder.shared.types import TourHeaderData

_COURSE_DATE_RE = re.compile(
    r"^\s*([A-Z]{1,2}\d{3}[A-Z]{0,2})\s+(\d{2})-(\d{2})-(\d{2})\s*[～~]\s*\d{2}-\d{2}-\d{2}",
    re.MULTILINE,
)
_TOUR_NAME_RE = re.compile(
    r"^\s*([A-Z]{1,2}\d{3}[A-Z]{0,2}\s+[A-Z]{2,4}\s+[A-Z]{2,4}\s+.+?DAYS)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_COURSE_LINE_HINT_RE = re.compile(r"\b[A-Z]{1,2}\d{3}[A-Z]{0,2}\b")
_VALID_TOUR_REF_RE = re.compile(r"^[A-Z]{1,2}\d{3}[A-Z]{0,2}\s+\d{4}$")
_INQUIRY_LIKE_RE = re.compile(r"\b\d{7,10}(?:-\d{3})?\b")
_TITLE_RE = re.compile(r"\b(MR|MS|MRS|MISS)\.?\b", re.IGNORECASE)
_SPACED_NAME_RE = re.compile(r"(^|[^A-Z])N\s*A\s*M\s*E([^A-Z]|$)", re.IGNORECASE)
_NO_HEADER_PREFIX_RE = re.compile(r"^NO(?:\b|[^A-Z0-9])", re.IGNORECASE)


def _is_guest_table_header_line(line: str) -> bool:
    upper = line.upper()
    if "TOUR NAME" in upper:
        return False
    if "問合せNO" in upper:
        return True
    if _NO_HEADER_PREFIX_RE.match(upper):
        return True
    if _SPACED_NAME_RE.search(upper):
        return "問合せ" in line or bool(_NO_HEADER_PREFIX_RE.match(upper))
    return False


def build_header_excerpt(rl_text: str) -> str:
    """Extract header-relevant lines from rooming list text, stopping at guest table."""
    lines = [line.strip() for line in rl_text.splitlines() if line.strip()]
    selected: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if _is_guest_table_header_line(line):
            break
        if _INQUIRY_LIKE_RE.search(line) or _TITLE_RE.search(line):
            continue
        upper = line.upper()
        has_course_hint = bool(_COURSE_LINE_HINT_RE.search(upper))
        if has_course_hint and not ("DAYS" in upper or re.search(r"\d{2}-\d{2}-\d{2}", line)):
            has_course_hint = False
        if (
            "ROOMING" in upper
            or "TOUR" in upper
            or "TOTAL" in upper
            or "DAYS" in upper
            or "FLTパターン" in line
            or "HTLパターン" in line
            or has_course_hint
        ):
            normalized = collapse_ws(line)
            if normalized not in seen:
                selected.append(normalized)
                seen.add(normalized)
        if len(selected) >= 60:
            break
    return "\n".join(selected[:60])


def extract_tour_header_rule(rl_text: str) -> TourHeaderData | None:
    """Extract tour header using regex rules only (no LLM). Returns None if nothing found."""
    course_match = _COURSE_DATE_RE.search(rl_text)
    tour_name_match = _TOUR_NAME_RE.search(rl_text)
    tour_ref = None
    if course_match:
        course_code = course_match.group(1).upper()
        month = course_match.group(3)
        day = course_match.group(4)
        tour_ref = f"{course_code} {month}{day}"
    tour_name = collapse_ws(tour_name_match.group(1)) if tour_name_match else None

    if not tour_ref and not tour_name:
        return None
    confidence = 0.95 if (tour_ref and tour_name) else 0.72
    return TourHeaderData(tour_ref=tour_ref, tour_name=tour_name, confidence=confidence)


def normalize_tour_header_candidate(candidate: dict[str, object]) -> TourHeaderData | None:
    """Validate and normalize a tour header candidate (from rule or LLM extraction)."""
    tour_ref_raw = candidate.get("tour_ref")
    tour_name_raw = candidate.get("tour_name")
    confidence_raw = candidate.get("confidence")

    tour_ref = collapse_ws(str(tour_ref_raw)).upper() if isinstance(tour_ref_raw, str) else None
    if tour_ref and not _VALID_TOUR_REF_RE.fullmatch(tour_ref):
        tour_ref = None

    tour_name = collapse_ws(str(tour_name_raw)) if isinstance(tour_name_raw, str) else None
    if tour_name == "":
        tour_name = None

    if isinstance(confidence_raw, bool):
        return None
    confidence = float(confidence_raw) if isinstance(confidence_raw, int | float) else None
    if confidence is None:
        return None
    if confidence < 0 or confidence > 1:
        return None
    if not tour_ref and not tour_name:
        return None
    return TourHeaderData(tour_ref=tour_ref, tour_name=tour_name, confidence=confidence)
