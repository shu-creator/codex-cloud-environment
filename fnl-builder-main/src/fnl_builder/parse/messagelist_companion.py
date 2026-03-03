from __future__ import annotations

import re
import unicodedata
from typing import Protocol

from fnl_builder.parse.messagelist_rules import _is_pdf_next_record_line
from fnl_builder.shared.text import normalize_inquiry_main

_COMPANION_END_RE = re.compile(r"と同\s*(?:ｸﾞﾙｰﾌﾟ|グループ|GRP|ＧＲＰ|室)", re.IGNORECASE)
_COMPANION_INQ_RE = re.compile(r"[#＃](\d{7,8})")
_DATE_PREFIX_RE = re.compile(r"^\d{2}-\d{2}\s")


class _CompanionResultLike(Protocol):
    companion_groups: dict[str, set[str]]


class _CompanionStateLike(Protocol):
    current_inquiry: str | None
    in_companion_section: bool
    companion_inquiries: set[str]


def _normalize_message_list_inquiry(raw: str) -> str:
    return normalize_inquiry_main(raw)


def companion_marker_flags(line: str) -> tuple[bool, bool]:
    normalized = unicodedata.normalize("NFKC", line or "")
    has_explicit_marker = "別問合せ番号同行" in normalized or "別問番同行" in normalized or "同行GRP" in normalized
    has_end_marker = bool(_COMPANION_END_RE.search(normalized))
    return has_explicit_marker, has_end_marker


def extract_companion_inquiries(line: str) -> set[str]:
    return {_normalize_message_list_inquiry(companion) for companion in _COMPANION_INQ_RE.findall(line)}


def store_companion_group(result: _CompanionResultLike, group: set[str]) -> None:
    if len(group) < 2:
        return
    for inquiry in group:
        result.companion_groups.setdefault(inquiry, set()).update(group - {inquiry})


def flush_companion_section(
    result: _CompanionResultLike,
    state: _CompanionStateLike,
) -> None:
    state.in_companion_section = False
    if state.current_inquiry and state.companion_inquiries:
        state.companion_inquiries.add(state.current_inquiry)
        store_companion_group(result, state.companion_inquiries)
    state.companion_inquiries = set()


def _is_companion_section_boundary(line: str) -> bool:
    return bool(_DATE_PREFIX_RE.match(line) or _is_pdf_next_record_line(line))


def handle_inline_companion_markers(
    result: _CompanionResultLike,
    state: _CompanionStateLike,
    *,
    has_explicit_marker: bool,
    has_end_marker: bool,
    line_companions: set[str],
) -> bool:
    if not (has_explicit_marker or (has_end_marker and line_companions)):
        return False

    if has_end_marker and line_companions:
        if state.current_inquiry:
            line_companions.add(state.current_inquiry)
        store_companion_group(result, line_companions)
        return False

    if has_explicit_marker and not has_end_marker:
        state.in_companion_section = True
        state.companion_inquiries = line_companions
        return True

    return False


def process_message_list_companions(
    line: str,
    result: _CompanionResultLike,
    state: _CompanionStateLike,
) -> bool:
    has_explicit_marker, has_end_marker = companion_marker_flags(line)
    line_companions: set[str] = set()
    if has_explicit_marker or has_end_marker:
        line_companions = extract_companion_inquiries(line)

    if handle_inline_companion_markers(
        result,
        state,
        has_explicit_marker=has_explicit_marker,
        has_end_marker=has_end_marker,
        line_companions=line_companions,
    ):
        return True

    if not state.in_companion_section:
        return False

    if _is_companion_section_boundary(line):
        flush_companion_section(result, state)
        return False

    state.companion_inquiries.update(extract_companion_inquiries(line))
    if has_end_marker:
        flush_companion_section(result, state)
    elif "部屋割り" in line:
        state.in_companion_section = False
        state.companion_inquiries = set()
    return False


def prune_companion_groups(
    companion_groups: dict[str, set[str]],
    known_output_inquiries: set[str],
) -> tuple[dict[str, set[str]], int]:
    known = {_normalize_message_list_inquiry(inquiry) for inquiry in known_output_inquiries if inquiry}
    if not known:
        return {}, sum(len(companions) for companions in companion_groups.values())

    pruned: dict[str, set[str]] = {}
    removed_edges = 0
    for inquiry, companions in companion_groups.items():
        inquiry_norm = _normalize_message_list_inquiry(inquiry)
        if inquiry_norm not in known:
            removed_edges += len(companions)
            continue
        kept: set[str] = set()
        for companion in companions:
            companion_norm = _normalize_message_list_inquiry(companion)
            if companion_norm in known and companion_norm != inquiry_norm:
                kept.add(companion_norm)
            else:
                removed_edges += 1
        if kept:
            pruned[inquiry_norm] = kept
    return pruned, removed_edges
