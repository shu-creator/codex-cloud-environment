from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from fnl_builder.shared.io import atomic_write_text
from fnl_builder.shared.types import AuditLog, GuestRecord, Issue, RoomingData


def write_audit_log(
    audit: AuditLog,
    audit_path: Path | None,
    *,
    guest_count: int = 0,
    status: str = "completed",
) -> None:
    if not audit_path:
        return
    data = asdict(audit)
    data["guest_count"] = guest_count
    data["status"] = status
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if status == "error":
        data["aborted_at"] = timestamp
    else:
        data["finished_at"] = timestamp
    atomic_write_text(audit_path, json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _append_missing_guest_data_issues(guests: list[GuestRecord], issues: list[Issue]) -> None:
    for guest in guests:
        missing_fields: list[str] = []
        if not guest.family_name:
            missing_fields.append("family_name")
        if not guest.given_name:
            missing_fields.append("given_name")
        if not guest.passport_no:
            missing_fields.append("passport_no")
        if not guest.issue_date:
            missing_fields.append("issue_date")
        if not guest.expiry_date:
            missing_fields.append("expiry_date")
        if not guest.course_code:
            missing_fields.append("course_code")
        if missing_fields:
            issues.append(
                Issue(level="warning", code="missing_guest_data", message=f"データ欠落: {', '.join(missing_fields)}")
            )


def _append_note_reference_issues(
    rooming: RoomingData, guests: list[GuestRecord], issues: list[Issue]
) -> None:
    guest_keys = {guest.inquiry.normalized() for guest in guests}
    guest_main_keys = {guest.inquiry.main for guest in guests}
    for note_key in rooming.notes_by_inquiry:
        if note_key in guest_keys or note_key in guest_main_keys:
            continue
        issues.append(
            Issue(
                level="error",
                code="note_inquiry_missing",
                message="RoomingList注記の問合せNOがゲスト一覧に存在しません。",
            )
        )


def _output_counts(guests: list[GuestRecord]) -> tuple[int, int, dict[str, int]]:
    out_pax = len(guests)
    out_room_groups = len({g.room_group_id for g in guests if g.room_group_id})
    out_rooms_by_type: dict[str, int] = {}
    seen_groups: set[str] = set()
    for guest in guests:
        if not guest.room_group_id or guest.room_group_id in seen_groups:
            continue
        seen_groups.add(guest.room_group_id)
        if guest.room_type:
            out_rooms_by_type[guest.room_type] = out_rooms_by_type.get(guest.room_type, 0) + 1
    return out_pax, out_room_groups, out_rooms_by_type


def _append_pax_mismatch_issue(rooming: RoomingData, out_pax: int, issues: list[Issue]) -> None:
    if rooming.declared_total_pax is None or rooming.declared_total_pax == out_pax:
        return
    issues.append(
        Issue(level="error", code="pax_mismatch", message=f"Total PAX不一致: 申告={rooming.declared_total_pax} 出力={out_pax}")
    )


def _append_room_count_mismatch_issues(
    rooming: RoomingData,
    out_room_groups: int,
    out_rooms_by_type: dict[str, int],
    issues: list[Issue],
) -> None:
    if not rooming.declared_rooms_by_type:
        return
    declared_total_rooms = sum(rooming.declared_rooms_by_type.values())
    if abs(declared_total_rooms - out_room_groups) > 0:
        issues.append(
            Issue(
                level="warning",
                code="rooms_mismatch_total",
                message=f"Total Rooms不一致: 申告={declared_total_rooms} 出力={out_room_groups}",
            )
        )
    for room_type, declared_n in rooming.declared_rooms_by_type.items():
        out_n = out_rooms_by_type.get(room_type, 0)
        if abs(declared_n - out_n) > 0:
            issues.append(
                Issue(
                    level="warning",
                    code="rooms_mismatch_by_type",
                    message=f"{room_type}部屋数不一致: 申告={declared_n} 出力={out_n}",
                )
            )


def process_audit_warnings(
    rooming: RoomingData,
    guests: list[GuestRecord],
    issues: list[Issue],
) -> tuple[int, int, dict[str, int]]:
    _append_missing_guest_data_issues(guests, issues)
    _append_note_reference_issues(rooming, guests, issues)
    out_pax, out_room_groups, out_rooms_by_type = _output_counts(guests)
    _append_pax_mismatch_issue(rooming, out_pax, issues)
    _append_room_count_mismatch_issues(rooming, out_room_groups, out_rooms_by_type, issues)
    return out_pax, out_room_groups, out_rooms_by_type
