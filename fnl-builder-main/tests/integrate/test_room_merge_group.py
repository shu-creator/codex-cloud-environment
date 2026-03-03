"""Tests for room merge group application."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_group import merge_room_groups, prioritize_room_merge_infos
from fnl_builder.shared.types import GuestRecord, InquiryKey, Issue, RoomMergeInfo


def _guest(inquiry: str, group_id: str, room_type: str = "TWN") -> GuestRecord:
    return GuestRecord(
        inquiry=InquiryKey(main=inquiry),
        full_name="TEST",
        family_name="TEST",
        given_name="",
        room_group_id=group_id,
        room_type=room_type,
    )


class TestPrioritizeRoomMergeInfos:
    def test_rule_id_beats_rule_name(self) -> None:
        infos = [
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="rule_name"),
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="rule_id"),
        ]
        result = prioritize_room_merge_infos(infos)
        assert len(result) == 1
        assert result[0].source == "rule_id"

    def test_rule_name_beats_llm_name(self) -> None:
        infos = [
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="llm_name"),
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="rule_name"),
        ]
        result = prioritize_room_merge_infos(infos)
        assert len(result) == 1
        assert result[0].source == "rule_name"

    def test_room_type_tiebreak(self) -> None:
        infos = [
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="rule_id"),
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="rule_id", room_type="TWN"),
        ]
        result = prioritize_room_merge_infos(infos)
        assert len(result) == 1
        assert result[0].room_type == "TWN"

    def test_llm_confidence_tiebreak(self) -> None:
        infos = [
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="llm_name", confidence=0.5),
            RoomMergeInfo(inquiries=frozenset({"1", "2"}), source="llm_name", confidence=0.9),
        ]
        result = prioritize_room_merge_infos(infos)
        assert len(result) == 1
        assert result[0].confidence == 0.9

    def test_single_inquiry_filtered(self) -> None:
        infos = [RoomMergeInfo(inquiries=frozenset({"1"}), source="rule_id")]
        result = prioritize_room_merge_infos(infos)
        assert len(result) == 0


class TestMergeRoomGroups:
    def test_basic_merge(self) -> None:
        guests = [
            _guest("100", "G1"),
            _guest("200", "G2"),
        ]
        infos = [RoomMergeInfo(inquiries=frozenset({"100", "200"}), source="rule_id")]
        issues: list[Issue] = []
        merge_room_groups(guests, infos, issues)
        assert guests[0].room_group_id == guests[1].room_group_id
        assert not issues

    def test_no_infos(self) -> None:
        guests = [_guest("100", "G1")]
        issues: list[Issue] = []
        merge_room_groups(guests, [], issues)
        assert guests[0].room_group_id == "G1"

    def test_ambiguous_normalization(self) -> None:
        # Two guests with same normalized inquiry but different originals
        guests = [
            _guest("0100", "G1"),
            _guest("100", "G2"),
            _guest("200", "G3"),
        ]
        infos = [RoomMergeInfo(inquiries=frozenset({"100", "200"}), source="rule_id")]
        issues: list[Issue] = []
        merge_room_groups(guests, infos, issues)
        # Should warn about ambiguous normalization
        assert any(i.code == "room_merge_ambiguous" for i in issues)

    def test_multiple_groups_ambiguous(self) -> None:
        guests = [
            _guest("100", "G1", "TWN"),
            _guest("100", "G2", "SGL"),
            _guest("200", "G3", "TWN"),
        ]
        infos = [RoomMergeInfo(inquiries=frozenset({"100", "200"}), source="rule_id")]
        issues: list[Issue] = []
        merge_room_groups(guests, infos, issues)
        assert any(i.code == "room_merge_ambiguous" for i in issues)
