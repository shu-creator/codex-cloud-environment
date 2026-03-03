from __future__ import annotations

import re

from fnl_builder.shared.text import collapse_ws, normalize_inquiry_main
from fnl_builder.shared.types import GuestRecord


def is_tour_conductor(guest: GuestRecord) -> bool:
    remarks_text = " ".join(guest.remarks_parts)
    full_text = f"{guest.full_name} {remarks_text}".upper()
    if re.search(r"\bT[/.]?C\b", full_text):
        return True
    if re.search(r"添乗員|ツアーコンダクター", guest.full_name + remarks_text):
        return True
    return False


def convert_sgl_to_tsu(guests: list[GuestRecord]) -> None:
    for guest in guests:
        if guest.room_type == "SGL" and not is_tour_conductor(guest):
            guest.room_type = "TSU"


def assign_room_numbers(guests: list[GuestRecord]) -> None:
    room_type_counter: dict[str, int] = {}
    seen_groups: set[str] = set()

    for guest in guests:
        if not guest.room_group_id or guest.room_group_id in seen_groups:
            continue
        seen_groups.add(guest.room_group_id)

        room_type = guest.room_type or "UNKNOWN"
        room_type_counter[room_type] = room_type_counter.get(room_type, 0) + 1
        guest.room_number = str(room_type_counter[room_type])


def guest_display_name(guest: GuestRecord) -> str:
    if guest.family_name:
        return collapse_ws(f"{guest.family_name} {guest.given_name}")
    return collapse_ws(guest.full_name)


def _build_room_group_guests(guests: list[GuestRecord]) -> dict[str, list[GuestRecord]]:
    room_group_guests: dict[str, list[GuestRecord]] = {}
    for guest in guests:
        room_group_id = guest.room_group_id
        if not room_group_id:
            continue
        room_group_guests.setdefault(room_group_id, []).append(guest)
    return room_group_guests


def _build_room_group_info(guests: list[GuestRecord]) -> dict[str, tuple[str, str]]:
    room_group_info: dict[str, tuple[str, str]] = {}
    for guest in guests:
        room_group_id = guest.room_group_id
        if not room_group_id:
            continue
        room_type = guest.room_type or ""
        room_number = guest.room_number or ""
        if room_group_id not in room_group_info:
            room_group_info[room_group_id] = (room_type, room_number)
            continue
        _, existing_room_number = room_group_info[room_group_id]
        if room_number and not existing_room_number:
            room_group_info[room_group_id] = (room_type, room_number)
    return room_group_info


def _insert_unique_same_room_note(guest: GuestRecord, room_note: str) -> None:
    if room_note not in guest.remarks_parts:
        guest.remarks_parts.insert(0, room_note)


def _insert_unique_companion_note(guest: GuestRecord, companion_note: str) -> None:
    if companion_note in guest.remarks_parts:
        return
    insert_pos = 0
    for idx, part in enumerate(guest.remarks_parts):
        if part.startswith("[同室]"):
            insert_pos = idx + 1
            break
    guest.remarks_parts.insert(insert_pos, companion_note)


def _build_same_room_note(guest: GuestRecord, group_guests: list[GuestRecord]) -> str | None:
    guest_inquiry = normalize_inquiry_main(guest.inquiry.main)
    roommate_names: list[str] = []
    for roommate in group_guests:
        roommate_inquiry = normalize_inquiry_main(roommate.inquiry.main)
        if roommate_inquiry == guest_inquiry:
            continue
        name = guest_display_name(roommate)
        if name:
            roommate_names.append(name)
    if not roommate_names:
        return None
    return f"[同室] {', '.join(roommate_names)}様と{guest.room_type or ''}同室"


def _apply_same_room_notes(room_group_guests: dict[str, list[GuestRecord]]) -> None:
    for group_guests in room_group_guests.values():
        inquiries_in_group = {normalize_inquiry_main(guest.inquiry.main) for guest in group_guests}
        if len(inquiries_in_group) <= 1:
            continue
        for guest in group_guests:
            room_note = _build_same_room_note(guest, group_guests)
            if room_note:
                _insert_unique_same_room_note(guest, room_note)


def _group_guests_by_inquiry(guests: list[GuestRecord]) -> dict[str, list[GuestRecord]]:
    grouped: dict[str, list[GuestRecord]] = {}
    for guest in guests:
        grouped.setdefault(normalize_inquiry_main(guest.inquiry.main), []).append(guest)
    return grouped


def _format_companion_room_info(
    room_group_id: str,
    room_group_info: dict[str, tuple[str, str]],
) -> str:
    room_type, room_number = room_group_info.get(room_group_id, ("", ""))
    if room_type and room_number:
        return f"{room_type}/No.{room_number}"
    return room_type or ""


def _collect_companions_in_other_rooms(
    guest: GuestRecord,
    companions: set[str],
    guests_by_inquiry: dict[str, list[GuestRecord]],
    room_group_info: dict[str, tuple[str, str]],
) -> list[str]:
    my_room_group_id = guest.room_group_id
    companion_names: list[str] = []
    for companion_inquiry in sorted(companions):
        for companion_guest in guests_by_inquiry.get(companion_inquiry, []):
            companion_room_group_id = companion_guest.room_group_id
            if not companion_room_group_id or companion_room_group_id == my_room_group_id:
                continue
            name = guest_display_name(companion_guest)
            room_info = _format_companion_room_info(companion_room_group_id, room_group_info)
            if room_info:
                companion_names.append(f"{name}様({room_info})")
            else:
                companion_names.append(f"{name}様")
    return companion_names


def _apply_companion_room_notes(
    guests: list[GuestRecord],
    companion_groups: dict[str, set[str]],
    room_group_info: dict[str, tuple[str, str]],
) -> None:
    if not companion_groups:
        return
    guests_by_inquiry = _group_guests_by_inquiry(guests)
    for guest in guests:
        guest_inquiry = normalize_inquiry_main(guest.inquiry.main)
        companions = companion_groups.get(guest_inquiry)
        if not companions:
            continue
        companions_in_other_rooms = _collect_companions_in_other_rooms(
            guest,
            companions - {guest_inquiry},
            guests_by_inquiry,
            room_group_info,
        )
        if not companions_in_other_rooms:
            continue
        companion_note = f"[同行GRP別室] {', '.join(companions_in_other_rooms)}"
        _insert_unique_companion_note(guest, companion_note)


def add_room_sharing_remarks(
    guests: list[GuestRecord],
    companion_groups: dict[str, set[str]],
) -> None:
    room_group_guests = _build_room_group_guests(guests)
    room_group_info = _build_room_group_info(guests)
    _apply_same_room_notes(room_group_guests)
    _apply_companion_room_notes(guests, companion_groups, room_group_info)
