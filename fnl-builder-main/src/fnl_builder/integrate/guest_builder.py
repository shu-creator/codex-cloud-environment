from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from fnl_builder.integrate.remark_rewrite import _append_unique_remarks
from fnl_builder.integrate.remark_rewrite import _is_fnl_shared_remark
from fnl_builder.integrate.remark_rewrite import _rewrite_remarks
from fnl_builder.integrate.remark_rewrite import _sanitize_remarks_parts
from fnl_builder.integrate.room_sharing import add_room_sharing_remarks
from fnl_builder.integrate.room_sharing import assign_room_numbers
from fnl_builder.integrate.room_sharing import convert_sgl_to_tsu
from fnl_builder.integrate.room_sharing import guest_display_name
from fnl_builder.integrate.vip import _resolve_vip_merge
from fnl_builder.resolve.inquiry_match import pick_best_inquiry_match
from fnl_builder.shared.text import collapse_ws, normalize_inquiry_main
from fnl_builder.shared.types import GuestRecord, Issue, LLMItem, PassportRecord, RewriteStats

_OP_RQ_PATTERN = re.compile(r"OP|RQ|ＯＰ|ＲＱ")


@dataclass
class GuestIntegrationState:
    guest_count_by_main: dict[str, int]
    guest_index_by_match_key: dict[str, int] = field(default_factory=dict)
    guest_position_by_main: dict[str, int] = field(default_factory=dict)
    op_rq_warned_inquiries: set[str] = field(default_factory=set)


def _build_guest_integration_state(rooming_guests: list[GuestRecord]) -> GuestIntegrationState:
    guest_count_by_main: dict[str, int] = {}
    for guest in rooming_guests:
        guest_count_by_main[guest.inquiry.main] = guest_count_by_main.get(guest.inquiry.main, 0) + 1
    return GuestIntegrationState(guest_count_by_main=guest_count_by_main)


def _resolve_guest_position(guest: GuestRecord, state: GuestIntegrationState) -> tuple[str, str]:
    inquiry_main = normalize_inquiry_main(guest.inquiry.main)
    state.guest_position_by_main[inquiry_main] = state.guest_position_by_main.get(inquiry_main, 0) + 1
    if guest.inquiry.branch:
        if guest.inquiry.branch.isdigit():
            return inquiry_main, str(int(guest.inquiry.branch))
        return inquiry_main, guest.inquiry.branch
    return inquiry_main, str(state.guest_position_by_main[inquiry_main])


def _append_rooming_notes(
    guest: GuestRecord,
    rooming_notes_by_inquiry: dict[str, list[str]],
    *,
    state: GuestIntegrationState,
    issues: list[Issue],
) -> None:
    _, note_list, note_amb = pick_best_inquiry_match(
        rooming_notes_by_inquiry,
        guest.inquiry,
        guest_count_by_main=state.guest_count_by_main,
    )
    if note_amb:
        issues.append(
            Issue(
                level="warning",
                code="inquiry_branch_ambiguous_rooming_notes",
                message="RoomingList注記の枝番照合が曖昧です。フォールバック候補を適用しました。",
            )
        )
    for note in note_list or []:
        guest.remarks_parts.append(note)


def _append_passenger_flags(
    guest: GuestRecord,
    passenger_flags_by_inquiry: dict[str, list[str]],
    *,
    state: GuestIntegrationState,
    issues: list[Issue],
) -> None:
    _, flags, flags_amb = pick_best_inquiry_match(
        passenger_flags_by_inquiry,
        guest.inquiry,
        guest_count_by_main=state.guest_count_by_main,
    )
    if flags_amb:
        issues.append(
            Issue(
                level="warning",
                code="inquiry_branch_ambiguous_passenger_flags",
                message="PassengerListフラグの枝番照合が曖昧です。",
            )
        )
    for flag in flags or []:
        guest.remarks_parts.append(flag)


def _append_messagelist_remarks(
    guest: GuestRecord,
    *,
    remarks_by_inquiry: dict[str, list[str]],
    remarks_by_inquiry_guest: dict[tuple[str, str], list[str]],
    llm_notes_by_guest: dict[tuple[str, str], list[str]],
    llm_items_by_guest: dict[tuple[str, str], list[LLMItem]],
    llm_extraction_success: bool,
    inquiry_key: str,
    guest_position: str,
    issues: list[Issue],
) -> RewriteStats:
    llm_key = (inquiry_key, guest_position)
    candidate_remarks = list(remarks_by_inquiry_guest.get(llm_key, []))
    if not candidate_remarks:
        # Fall back to inquiry-level remarks only when no guest-level entries
        # exist for this inquiry (i.e. CSV source which lacks guest identification).
        # When guest-level data exists (PDF source), remarks_by_inquiry conflates
        # shared and guest-specific remarks, so fallback would cause cross-guest leakage.
        has_guest_level = any(k[0] == inquiry_key for k in remarks_by_inquiry_guest)
        if not has_guest_level:
            candidate_remarks = list(remarks_by_inquiry.get(inquiry_key, []))
    guest_llm_remarks = llm_notes_by_guest.get(llm_key, [])
    guest_llm_items = llm_items_by_guest.get(llm_key, [])
    vip_mode_active = False
    generated_vip_remarks: list[str] = []
    if llm_extraction_success:
        candidate_remarks, vip_mode_active, generated_vip_remarks = _resolve_vip_merge(
            candidate_remarks,
            guest_llm_items,
            issues=issues,
        )
    rewritten_remarks, rewrite_stats = _rewrite_remarks(
        candidate_remarks,
        guest_llm_remarks=guest_llm_remarks,
        guest_llm_items=guest_llm_items,
        llm_extraction_success=llm_extraction_success,
        skip_vip_label=vip_mode_active,
    )
    if generated_vip_remarks:
        _append_unique_remarks(rewritten_remarks, generated_vip_remarks)
    _append_unique_remarks(guest.remarks_parts, rewritten_remarks)
    return rewrite_stats


def _apply_course_code_from_messagelist(
    guest: GuestRecord,
    *,
    course_by_inquiry: dict[str, str],
    inquiry_key: str,
) -> None:
    if inquiry_key in course_by_inquiry:
        guest.course_code = course_by_inquiry[inquiry_key]
    elif guest.inquiry.main in course_by_inquiry:
        guest.course_code = course_by_inquiry[guest.inquiry.main]


def _apply_passenger_guest_data(
    guest: GuestRecord,
    passenger_guests_by_inquiry: dict[str, list[PassportRecord]],
    *,
    state: GuestIntegrationState,
    issues: list[Issue],
) -> None:
    matched_key, passenger_guests, passenger_amb = pick_best_inquiry_match(
        passenger_guests_by_inquiry,
        guest.inquiry,
        guest_count_by_main=state.guest_count_by_main,
    )
    if passenger_amb:
        issues.append(
            Issue(
                level="warning",
                code="inquiry_branch_ambiguous_passenger",
                message="PassengerListゲスト情報の枝番照合が曖昧です。",
            )
        )
    if not passenger_guests or matched_key is None:
        return

    guest_index = state.guest_index_by_match_key.get(matched_key, 0)
    state.guest_index_by_match_key[matched_key] = guest_index + 1
    if guest_index >= len(passenger_guests):
        return

    passenger_guest = passenger_guests[guest_index]
    guest.passport_no = passenger_guest.passport_no or None
    guest.issue_date = passenger_guest.issue_date or None
    guest.expiry_date = passenger_guest.expiry_date or None
    if passenger_guest.full_name and passenger_guest.full_name.strip():
        guest.full_name = passenger_guest.full_name
    if passenger_guest.family_name and passenger_guest.family_name.strip():
        guest.family_name = passenger_guest.family_name
    if passenger_guest.given_name and passenger_guest.given_name.strip():
        guest.given_name = passenger_guest.given_name


def _finalize_integrated_guest(
    guest: GuestRecord,
    *,
    state: GuestIntegrationState,
    issues: list[Issue],
    remarks_has_banned: Callable[[str], bool],
) -> None:
    guest.remarks_parts = _sanitize_remarks_parts(guest.remarks_parts)

    if any("PPT未" in part for part in guest.remarks_parts) and guest.passport_no:
        guest.remarks_parts = [part for part in guest.remarks_parts if "PPT未" not in part]

    non_fnl_shared_remarks = [part for part in guest.remarks_parts if not _is_fnl_shared_remark(part)]
    non_fnl_shared_text = collapse_ws(" ".join(non_fnl_shared_remarks))
    if non_fnl_shared_text and remarks_has_banned(non_fnl_shared_text):
        issues.append(
            Issue(
                level="error",
                code="remarks_banned",
                message="Remarksに禁止語句（支払/保険/領収書/社内…）が含まれています。",
            )
        )

    remarks_text = collapse_ws(" ".join(guest.remarks_parts))
    if _OP_RQ_PATTERN.search(remarks_text) and guest.inquiry.main not in state.op_rq_warned_inquiries:
        state.op_rq_warned_inquiries.add(guest.inquiry.main)
        issues.append(
            Issue(
                level="warning",
                code="op_rq_pending",
                message="OPがRQのまま未確定の記載があります。",
            )
        )


def process_integrate_guest_data(
    *,
    rooming_guests: list[GuestRecord],
    rooming_notes_by_inquiry: dict[str, list[str]],
    passenger_flags_by_inquiry: dict[str, list[str]],
    passenger_guests_by_inquiry: dict[str, list[PassportRecord]],
    remarks_by_inquiry: dict[str, list[str]],
    remarks_by_inquiry_guest: dict[tuple[str, str], list[str]],
    course_by_inquiry: dict[str, str],
    llm_notes_by_guest: dict[tuple[str, str], list[str]],
    llm_items_by_guest: dict[tuple[str, str], list[LLMItem]] = {},
    llm_extraction_success: bool,
    issues: list[Issue],
    guests_out: list[GuestRecord],
    remarks_has_banned: Callable[[str], bool],
) -> RewriteStats:
    state = _build_guest_integration_state(rooming_guests)
    rewrite_stats = RewriteStats()
    for guest in list(rooming_guests):
        inquiry_key, guest_position = _resolve_guest_position(guest, state)
        _append_rooming_notes(
            guest,
            rooming_notes_by_inquiry,
            state=state,
            issues=issues,
        )
        _append_passenger_flags(
            guest,
            passenger_flags_by_inquiry,
            state=state,
            issues=issues,
        )
        guest_rewrite_stats = _append_messagelist_remarks(
            guest,
            remarks_by_inquiry=remarks_by_inquiry,
            remarks_by_inquiry_guest=remarks_by_inquiry_guest,
            llm_notes_by_guest=llm_notes_by_guest,
            llm_items_by_guest=llm_items_by_guest,
            llm_extraction_success=llm_extraction_success,
            inquiry_key=inquiry_key,
            guest_position=guest_position,
            issues=issues,
        )
        rewrite_stats = RewriteStats(
            candidates=rewrite_stats.candidates + guest_rewrite_stats.candidates,
            applied=rewrite_stats.applied + guest_rewrite_stats.applied,
            fallback=rewrite_stats.fallback + guest_rewrite_stats.fallback,
        )
        _apply_course_code_from_messagelist(
            guest,
            course_by_inquiry=course_by_inquiry,
            inquiry_key=inquiry_key,
        )
        _apply_passenger_guest_data(
            guest,
            passenger_guests_by_inquiry,
            state=state,
            issues=issues,
        )
        _finalize_integrated_guest(
            guest,
            state=state,
            issues=issues,
            remarks_has_banned=remarks_has_banned,
        )
        guests_out.append(guest)
    return rewrite_stats


_FULL_WHO_ID_RE = re.compile(r"0*(\d{7,10})-(\d{3})")
_SHORT_INQUIRY_RE = re.compile(r"[#＃](\d{7,10})")


def _substitute_inquiry_refs_with_names(
    guests: list[GuestRecord],
) -> None:
    """Replace inquiry-number references in remarks with guest display names."""
    name_map: dict[str, str] = {}
    inquiry_name_map: dict[str, str] = {}
    for guest in guests:
        inq = normalize_inquiry_main(guest.inquiry.main)
        padded = inq.zfill(10)
        branch = guest.inquiry.branch
        name = guest_display_name(guest) + "様"
        if branch:
            name_map[f"{padded}-{branch}"] = name
        else:
            key = f"{padded}-001"
            if key in name_map:
                name_map[key] = ""
            else:
                name_map[key] = name
        if inq not in inquiry_name_map:
            inquiry_name_map[inq] = name
        else:
            inquiry_name_map[inq] = ""

    def _replace_refs(text: str) -> str:
        def _full_ref(m: re.Match[str]) -> str:
            key = f"{m.group(1).zfill(10)}-{m.group(2)}"
            resolved = name_map.get(key)
            return resolved if resolved else m.group(0)

        def _short_ref(m: re.Match[str]) -> str:
            inq = m.group(1).lstrip("0") or "0"
            resolved = inquiry_name_map.get(inq)
            return resolved if resolved else m.group(0)

        result = _FULL_WHO_ID_RE.sub(_full_ref, text)
        result = _SHORT_INQUIRY_RE.sub(_short_ref, result)
        return result

    for guest in guests:
        guest.remarks_parts = [_replace_refs(part) for part in guest.remarks_parts]


def process_post_room_grouping(
    *,
    guests: list[GuestRecord],
    companion_groups: dict[str, set[str]],
) -> None:
    min_inquiry_by_group: dict[str, str] = {}
    for guest in guests:
        if not guest.room_group_id:
            continue
        inquiry_main = normalize_inquiry_main(guest.inquiry.main)
        if guest.room_group_id not in min_inquiry_by_group:
            min_inquiry_by_group[guest.room_group_id] = inquiry_main
        elif inquiry_main < min_inquiry_by_group[guest.room_group_id]:
            min_inquiry_by_group[guest.room_group_id] = inquiry_main

    guest_inquiries = {normalize_inquiry_main(g.inquiry.main) for g in guests}
    companion_group_min: dict[str, str] = {}
    for guest in guests:
        inq = normalize_inquiry_main(guest.inquiry.main)
        companions = companion_groups.get(inq)
        if companions:
            known_members = (companions | {inq}) & guest_inquiries
            group_min = min(known_members) if known_members else inq
        else:
            group_min = inq
        companion_group_min[inq] = group_min

    def sort_key(guest: GuestRecord) -> tuple[int, str, str, str, str]:
        room_priority = {"TWN": 0, "DBL": 1, "TPL": 2, "TRP": 2, "TSU": 3, "SGL": 4}
        rt_order = room_priority.get(guest.room_type or "", 5)
        inq_for_sort = normalize_inquiry_main(guest.inquiry.main)
        comp_sort = companion_group_min.get(inq_for_sort, "9999999999")
        group_sort = min_inquiry_by_group.get(guest.room_group_id or "", "9999999999")
        digits_only = "".join(ch for ch in inq_for_sort if ch.isdigit()) or "0"
        inq_desc = "".join(chr(ord("9") - int(ch)) for ch in digits_only.zfill(15))
        return rt_order, comp_sort, group_sort, guest.room_group_id or "", inq_desc

    guests.sort(key=sort_key)
    convert_sgl_to_tsu(guests)
    assign_room_numbers(guests)
    add_room_sharing_remarks(guests, companion_groups)
    _substitute_inquiry_refs_with_names(guests)
