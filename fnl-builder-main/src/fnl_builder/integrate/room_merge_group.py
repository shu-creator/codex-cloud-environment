"""Apply room merge instructions to guest records."""
from __future__ import annotations

import re

from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import GuestRecord, Issue, RoomMergeInfo

_ROOM_TYPES_NONCAP = r"(?:TWN|DBL|SGL|TSU|TPL|TRP)"


def _normalize_room_type(room_type: str | None) -> str | None:
    if not room_type:
        return None
    normalized = room_type.upper().strip()
    if re.fullmatch(_ROOM_TYPES_NONCAP, normalized):
        return normalized
    return None


def prioritize_room_merge_infos(merge_infos: list[RoomMergeInfo]) -> list[RoomMergeInfo]:
    """Select highest-priority merge info per inquiry group."""
    priority = {"rule_id": 0, "rule_name": 1, "llm_name": 2}
    selected: dict[frozenset[str], RoomMergeInfo] = {}

    for info in merge_infos:
        normalized = frozenset(
            normalize_inquiry_main(i) for i in info.inquiries if i
        )
        if len(normalized) < 2:
            continue
        room_type = _normalize_room_type(info.room_type)
        candidate = RoomMergeInfo(
            inquiries=normalized,
            room_type=room_type,
            source=info.source,
            confidence=info.confidence,
        )
        current = selected.get(normalized)
        if current is None:
            selected[normalized] = candidate
            continue

        cur_pri = priority.get(current.source, 999)
        cand_pri = priority.get(candidate.source, 999)
        if cand_pri < cur_pri:
            selected[normalized] = candidate
        elif cand_pri == cur_pri:
            if current.room_type is None and candidate.room_type is not None:
                selected[normalized] = candidate
            elif (
                current.source == "llm_name"
                and candidate.source == "llm_name"
                and (candidate.confidence or 0.0) > (current.confidence or 0.0)
            ):
                selected[normalized] = candidate

    return list(selected.values())


def _build_guest_maps(
    guests: list[GuestRecord],
) -> tuple[dict[str, set[str]], dict[str, str], dict[str, set[str]]]:
    """Build lookup maps for room merge processing."""
    inquiry_to_groups: dict[str, set[str]] = {}
    group_to_room_type: dict[str, str] = {}
    normalized_to_originals: dict[str, set[str]] = {}

    for guest in guests:
        inquiry = guest.inquiry.main
        group_id = guest.room_group_id or ""
        if group_id:
            inquiry_to_groups.setdefault(inquiry, set()).add(group_id)
            if group_id not in group_to_room_type and guest.room_type:
                group_to_room_type[group_id] = guest.room_type.upper()
        normalized = normalize_inquiry_main(inquiry)
        normalized_to_originals.setdefault(normalized, set()).add(inquiry)

    return inquiry_to_groups, group_to_room_type, normalized_to_originals


def _resolve_original_inquiries(
    inquiries: frozenset[str],
    normalized_to_originals: dict[str, set[str]],
) -> tuple[set[str], int]:
    originals: set[str] = set()
    ambiguous = 0
    for inq in inquiries:
        mapped = normalized_to_originals.get(normalize_inquiry_main(inq))
        if not mapped:
            continue
        if len(mapped) > 1:
            ambiguous += 1
            continue
        originals.add(next(iter(mapped)))
    return originals, ambiguous


def _select_groups_to_merge(
    original_inquiries: set[str],
    inquiry_to_groups: dict[str, set[str]],
    group_to_room_type: dict[str, str],
    *,
    room_type: str | None,
) -> tuple[dict[str, str], bool]:
    selected: dict[str, str] = {}
    for inquiry in original_inquiries:
        candidates = set(inquiry_to_groups.get(inquiry, set()))
        if room_type:
            norm_rt = room_type.upper()
            candidates = {
                g for g in candidates
                if group_to_room_type.get(g, norm_rt) == norm_rt
            }
        if not candidates:
            continue
        if len(candidates) > 1:
            return {}, True
        selected[inquiry] = next(iter(candidates))
    return selected, False


def merge_room_groups(
    guests: list[GuestRecord],
    merge_infos: list[RoomMergeInfo],
    issues: list[Issue],
) -> None:
    """Apply room merge instructions to guest records in-place."""
    if not merge_infos:
        return

    for info in merge_infos:
        inq_to_groups, grp_to_rt, norm_to_orig = _build_guest_maps(guests)
        originals, ambiguous = _resolve_original_inquiries(info.inquiries, norm_to_orig)

        if ambiguous > 0:
            issues.append(Issue(
                level="warning",
                code="room_merge_ambiguous",
                message=f"問合せNOの正規化が曖昧なため部屋マージをスキップしました（{ambiguous}件）。",
            ))
            continue

        selected, sel_ambiguous = _select_groups_to_merge(
            originals, inq_to_groups, grp_to_rt, room_type=info.room_type,
        )
        if sel_ambiguous:
            issues.append(Issue(
                level="warning",
                code="room_merge_ambiguous",
                message="同一問合せ内に複数部屋があるため部屋マージをスキップしました。",
            ))
            continue

        involved = set(selected.values())
        if len(involved) < 2:
            continue
        primary = min(involved)
        updates = {g: primary for g in involved if g != primary}

        for guest in guests:
            current = guest.room_group_id or ""
            new = updates.get(current)
            if new:
                guest.room_group_id = new
