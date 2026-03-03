"""Integration tests for room merge facade."""
from __future__ import annotations

from fnl_builder.integrate.room_merge import apply_room_merges
from fnl_builder.shared.types import GuestRecord, InquiryKey, Issue


def _guest(inquiry: str, group_id: str, room_type: str = "TWN") -> GuestRecord:
    return GuestRecord(
        inquiry=InquiryKey(main=inquiry),
        full_name="TEST",
        family_name="TEST",
        given_name="",
        room_group_id=group_id,
        room_type=room_type,
    )


class TestApplyRoomMerges:
    def test_id_based_merge(self) -> None:
        guests = [_guest("1234567890", "G1"), _guest("9876543210", "G2")]
        issues: list[Issue] = []
        apply_room_merges(
            ml_text="#1234567890と#9876543210 同室",
            guests=guests,
            known_inquiries={"1234567890", "9876543210"},
            llm_provider="none",
            issues=issues,
        )
        assert guests[0].room_group_id == guests[1].room_group_id

    def test_name_based_merge(self) -> None:
        guests = [_guest("1234567890", "G1"), _guest("9876543210", "G2")]
        issues: list[Issue] = []
        ml_text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        apply_room_merges(
            ml_text=ml_text,
            guests=guests,
            known_inquiries={"1234567890", "9876543210"},
            llm_provider="none",
            issues=issues,
        )
        assert guests[0].room_group_id == guests[1].room_group_id

    def test_no_ml_text(self) -> None:
        guests = [_guest("100", "G1")]
        issues: list[Issue] = []
        apply_room_merges(
            ml_text="",
            guests=guests,
            known_inquiries={"100"},
            llm_provider="none",
            issues=issues,
        )
        assert guests[0].room_group_id == "G1"

    def test_id_beats_name_priority(self) -> None:
        guests = [_guest("1234567890", "G1"), _guest("9876543210", "G2")]
        issues: list[Issue] = []
        ml_text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "#1234567890と#9876543210 同室\n"
            "TANAKAとSUZUKI 同室"
        )
        apply_room_merges(
            ml_text=ml_text,
            guests=guests,
            known_inquiries={"1234567890", "9876543210"},
            llm_provider="none",
            issues=issues,
        )
        # Both sources agree, merge should happen
        assert guests[0].room_group_id == guests[1].room_group_id

    def test_mock_llm_resolver(self) -> None:
        guests = [_guest("1234567890", "G1"), _guest("9876543210", "G2")]
        issues: list[Issue] = []
        ml_text = "TANAKAとSUZUKI 同室"
        apply_room_merges(
            ml_text=ml_text,
            guests=guests,
            known_inquiries={"1234567890", "9876543210"},
            llm_provider="mock",
            issues=issues,
        )
        # Mock resolver can't resolve without aliases, so no merge
        assert guests[0].room_group_id != guests[1].room_group_id
