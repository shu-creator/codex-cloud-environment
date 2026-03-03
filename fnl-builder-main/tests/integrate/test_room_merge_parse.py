"""Tests for room merge parsing from ML text."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_parse import parse_room_assignments


class TestParseRoomAssignments:
    def test_same_room_pair(self) -> None:
        text = "#1234567890と#9876543210 同室"
        result = parse_room_assignments(text)
        assert len(result) == 1
        assert frozenset({"1234567890", "9876543210"}) == result[0].inquiries
        assert result[0].source == "rule_id"

    def test_same_room_pair_with_room_type(self) -> None:
        text = "#1234567890と#9876543210 同室(TWN)"
        result = parse_room_assignments(text)
        assert len(result) == 1
        assert result[0].room_type == "TWN"

    def test_explicit_assignment_section(self) -> None:
        text = "部屋割り：\n#1234567890\n#9876543210\nが TWN"
        result = parse_room_assignments(text)
        assert len(result) == 1
        inqs = result[0].inquiries
        assert "1234567890" in inqs
        assert "9876543210" in inqs
        assert result[0].room_type == "TWN"

    def test_contextual_same_room(self) -> None:
        text = "1234567890-001\n#9876543210 同室\n"
        result = parse_room_assignments(text)
        assert len(result) == 1
        assert frozenset({"1234567890", "9876543210"}) == result[0].inquiries

    def test_csv_context_inquiry(self) -> None:
        text = "[問合せNO: 1234567890]\n#9876543210 同室"
        result = parse_room_assignments(text)
        assert len(result) == 1

    def test_dedup(self) -> None:
        text = "#1234567890と#9876543210 同室\n#1234567890と#9876543210 同室"
        result = parse_room_assignments(text)
        assert len(result) == 1

    def test_same_inquiry_ignored(self) -> None:
        text = "#1234567890と#1234567890 同室"
        result = parse_room_assignments(text)
        assert len(result) == 0

    def test_no_match(self) -> None:
        text = "普通のテキストです"
        result = parse_room_assignments(text)
        assert len(result) == 0

    def test_normalize_leading_zeros(self) -> None:
        text = "#0001234567と#0009876543 同室"
        result = parse_room_assignments(text)
        assert len(result) == 1
        inqs = result[0].inquiries
        assert "1234567" in inqs
        assert "9876543" in inqs

    def test_fullwidth_hash(self) -> None:
        text = "＃1234567890と＃9876543210 同室"
        result = parse_room_assignments(text)
        assert len(result) == 1
