from __future__ import annotations

import json
from pathlib import Path

from fnl_builder.render.audit import process_audit_warnings, write_audit_log
from fnl_builder.shared.types import (
    AuditLog,
    GuestRecord,
    InquiryKey,
    Issue,
    PipelineCounts,
    RoomingData,
)


def _make_audit() -> AuditLog:
    return AuditLog(
        started_at="2026-01-01T00:00:00Z",
        input_mode="files",
        input_files_sha256={},
        counts=PipelineCounts(),
    )


def test_write_audit_log_creates_json_file(tmp_path: Path) -> None:
    audit = _make_audit()
    out = tmp_path / "audit.json"
    write_audit_log(audit, out, guest_count=3)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["started_at"] == "2026-01-01T00:00:00Z"
    assert data["status"] == "completed"
    assert "finished_at" in data
    assert data["guest_count"] == 3


def test_write_audit_log_skips_none_path() -> None:
    audit = _make_audit()
    write_audit_log(audit, None)


def test_write_audit_log_error_status(tmp_path: Path) -> None:
    audit = _make_audit()
    out = tmp_path / "audit.json"
    write_audit_log(audit, out, status="error")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["status"] == "error"
    assert "aborted_at" in data
    assert "finished_at" not in data


def test_process_audit_warnings_missing_guest_data() -> None:
    guest = GuestRecord(
        inquiry=InquiryKey(main="10000001"),
        full_name="A B",
        family_name="A",
        given_name="B",
    )
    issues: list[Issue] = []
    process_audit_warnings(RoomingData.empty(), [guest], issues)
    codes = [i.code for i in issues]
    assert "missing_guest_data" in codes
    msg = next(i.message for i in issues if i.code == "missing_guest_data")
    assert "passport_no" in msg


def test_process_audit_warnings_pax_mismatch() -> None:
    guest = GuestRecord(
        inquiry=InquiryKey(main="10000001"),
        full_name="A B",
        family_name="A",
        given_name="B",
        passport_no="TR1234567",
        issue_date="2025-01-01",
        expiry_date="2035-01-01",
        course_code="E417",
    )
    rooming = RoomingData(declared_total_pax=5)
    issues: list[Issue] = []
    process_audit_warnings(rooming, [guest], issues)
    codes = [i.code for i in issues]
    assert "pax_mismatch" in codes


def test_process_audit_warnings_rooms_mismatch() -> None:
    guest = GuestRecord(
        inquiry=InquiryKey(main="10000001"),
        full_name="A B",
        family_name="A",
        given_name="B",
        room_type="TWN",
        room_group_id="g1",
        passport_no="TR1234567",
        issue_date="2025-01-01",
        expiry_date="2035-01-01",
        course_code="E417",
    )
    rooming = RoomingData(declared_rooms_by_type={"TWN": 3})
    issues: list[Issue] = []
    process_audit_warnings(rooming, [guest], issues)
    codes = [i.code for i in issues]
    assert "rooms_mismatch_total" in codes
    assert "rooms_mismatch_by_type" in codes


def test_process_audit_warnings_note_reference() -> None:
    rooming = RoomingData(notes_by_inquiry={"99999999": ["some note"]})
    issues: list[Issue] = []
    process_audit_warnings(rooming, [], issues)
    codes = [i.code for i in issues]
    assert "note_inquiry_missing" in codes


def test_process_audit_warnings_returns_counts() -> None:
    guest = GuestRecord(
        inquiry=InquiryKey(main="10000001"),
        full_name="A B",
        family_name="A",
        given_name="B",
        room_type="TWN",
        room_group_id="g1",
    )
    issues: list[Issue] = []
    out_pax, out_room_groups, out_rooms_by_type = process_audit_warnings(RoomingData.empty(), [guest], issues)
    assert out_pax == 1
    assert out_room_groups == 1
    assert out_rooms_by_type == {"TWN": 1}
