"""Parse room assignment instructions from message list text."""
from __future__ import annotations

import re

from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import RoomMergeInfo

_ROOM_TYPES_NONCAP = r"(?:TWN|DBL|SGL|TSU|TPL|TRP)"
_ROOM_ASSIGN_SECTION_SPLIT_RE = re.compile(r"(?=部屋割り[：:])")
_ROOM_ASSIGN_INQ_RE = re.compile(r"[#＃]?(\d{7,10})")
_ROOM_ASSIGN_RE = re.compile(
    rf"((?:\s*[#＃]?\d{{7,10}}[^\n]*\n?)+)\s*が\s*({_ROOM_TYPES_NONCAP})",
    re.IGNORECASE,
)
_SAME_ROOM_PAIR_RE = re.compile(
    rf"[#＃]?(\d{{7,10}})[^\d#＃\n]*[#＃]?(\d{{7,10}})[^\n]*同室"
    rf"(?:[（(]\s*\d*\s*({_ROOM_TYPES_NONCAP})\s*[)）])?",
    re.IGNORECASE,
)
_SAME_ROOM_SINGLE_RE = re.compile(
    rf"[#＃](\d{{7,10}})[^\n]*同室(?:[（(]\s*\d*\s*({_ROOM_TYPES_NONCAP})\s*[)）])?",
    re.IGNORECASE,
)
_CURRENT_INQUIRY_PDF_RE = re.compile(r"(\d{10})-(\d{3})")
_CURRENT_INQUIRY_CSV_RE = re.compile(r"\[問合せNO:\s*(\d{7,10})\]")


def _normalize(inquiry: str) -> str:
    return normalize_inquiry_main(inquiry)


def _extract_explicit_assignment(section: str) -> tuple[frozenset[str], str | None] | None:
    if not _ROOM_ASSIGN_INQ_RE.findall(section):
        return None
    m = _ROOM_ASSIGN_RE.search(section)
    if m is None:
        return None
    inqs = frozenset(_normalize(i) for i in _ROOM_ASSIGN_INQ_RE.findall(m.group(1)))
    if len(inqs) < 2:
        return None
    return inqs, m.group(2).upper()


def _extract_same_room_pairs(text: str) -> list[tuple[frozenset[str], str | None]]:
    merges: list[tuple[frozenset[str], str | None]] = []
    for m in _SAME_ROOM_PAIR_RE.finditer(text):
        inq1 = _normalize(m.group(1))
        inq2 = _normalize(m.group(2))
        room_type = (m.group(3) or "").upper() or None
        if inq1 != inq2:
            merges.append((frozenset({inq1, inq2}), room_type))
    return merges


def _extract_context_inquiry(line: str) -> str | None:
    pdf_m = _CURRENT_INQUIRY_PDF_RE.search(line)
    if pdf_m:
        return _normalize(pdf_m.group(1))
    csv_m = _CURRENT_INQUIRY_CSV_RE.search(line)
    if csv_m:
        return _normalize(csv_m.group(1))
    return None


def _extract_contextual_pairs(text: str) -> list[tuple[frozenset[str], str | None]]:
    merges: list[tuple[frozenset[str], str | None]] = []
    current_inquiry: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        ctx = _extract_context_inquiry(line)
        if ctx:
            current_inquiry = ctx
        if not current_inquiry:
            continue
        if len(_ROOM_ASSIGN_INQ_RE.findall(line)) >= 2:
            continue
        single_m = _SAME_ROOM_SINGLE_RE.search(line)
        if not single_m:
            continue
        target = _normalize(single_m.group(1))
        room_type = (single_m.group(2) or "").upper() or None
        if target != current_inquiry:
            merges.append((frozenset({current_inquiry, target}), room_type))
    return merges


def _dedupe(
    merges: list[tuple[frozenset[str], str | None]],
) -> list[tuple[frozenset[str], str | None]]:
    seen: set[tuple[frozenset[str], str | None]] = set()
    out: list[tuple[frozenset[str], str | None]] = []
    for inqs, rt in merges:
        key = (inqs, rt)
        if key not in seen:
            seen.add(key)
            out.append((inqs, rt))
    return out


def parse_room_assignments(text: str) -> list[RoomMergeInfo]:
    """Parse room assignment instructions from ML text.

    Detects:
    - Explicit ``部屋割り：`` sections with inquiry groups
    - ``#inq1と#inq2 同室`` pair patterns
    - Contextual single-inquiry ``#inq 同室`` with current inquiry context
    """
    raw_merges: list[tuple[frozenset[str], str | None]] = []

    for section in _ROOM_ASSIGN_SECTION_SPLIT_RE.split(text):
        if not section.startswith("部屋割り"):
            continue
        result = _extract_explicit_assignment(section)
        if result is not None:
            raw_merges.append(result)

    raw_merges.extend(_extract_same_room_pairs(text))
    raw_merges.extend(_extract_contextual_pairs(text))
    deduped = _dedupe(raw_merges)

    return [
        RoomMergeInfo(inquiries=inqs, room_type=rt, source="rule_id")
        for inqs, rt in deduped
    ]
