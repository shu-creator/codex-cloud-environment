"""Tests for name-based room merge alias extraction and rule resolution."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_name import (
    extract_name_room_candidates,
    normalize_alias_name,
    resolve_name_candidate_by_rule,
)


class TestNormalizeAliasName:
    def test_basic(self) -> None:
        assert normalize_alias_name("田中") == "田中"

    def test_strips_honorific(self) -> None:
        assert normalize_alias_name("田中様") == "田中"
        assert normalize_alias_name("田中さん") == "田中"

    def test_strips_prefix(self) -> None:
        assert normalize_alias_name("：田中") == "田中"
        assert normalize_alias_name(" - 田中") == "田中"

    def test_uppercase(self) -> None:
        assert normalize_alias_name("tanaka") == "TANAKA"

    def test_removes_separators(self) -> None:
        assert normalize_alias_name("田中・太郎") == "田中太郎"

    def test_nfkc(self) -> None:
        assert normalize_alias_name("Ｔａｎａｋａ") == "TANAKA"


class TestExtractNameRoomCandidates:
    def test_basic_name_pair(self) -> None:
        text = "TANAKAとSUZUKI 同室"
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        assert candidates[0].name_a == "TANAKA"
        assert candidates[0].name_b == "SUZUKI"

    def test_with_room_type(self) -> None:
        text = "TANAKAとSUZUKI 同室(TWN)"
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        assert candidates[0].room_type == "TWN"

    def test_same_name_ignored(self) -> None:
        text = "TANAKAとTANAKA 同室"
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 0

    def test_alias_context_accumulated(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        assert "TANAKA" in candidates[0].aliases_by_name
        assert "SUZUKI" in candidates[0].aliases_by_name

    def test_context_reset_on_new_inquiry(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "9876543210-001\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        # aliases_by_name resets per context; TANAKA only in first context
        assert "TANAKA" not in candidates[0].aliases_by_name

    def test_no_match(self) -> None:
        text = "普通のテキストです"
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 0

    def test_japanese_names(self) -> None:
        text = "田中と鈴木 同室"
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1


class TestResolveNameCandidateByRule:
    def test_resolves_with_aliases(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        known = {"1234567890", "9876543210"}
        result = resolve_name_candidate_by_rule(candidates[0], known)
        assert result is not None
        assert result.inquiries == frozenset({"1234567890", "9876543210"})
        assert result.source == "rule_name"

    def test_unknown_inquiry_skipped(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        known = {"1234567890"}  # 9876543210 not known
        result = resolve_name_candidate_by_rule(candidates[0], known)
        assert result is None

    def test_ambiguous_alias_skipped(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 TANAKA\n"
            "#1111111111 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        known = {"1234567890", "9876543210", "1111111111"}
        result = resolve_name_candidate_by_rule(candidates[0], known)
        # TANAKA maps to 2 inquiries -> ambiguous
        assert result is None

    def test_global_alias_fallback(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "9876543210-001\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        known = {"1234567890", "9876543210"}
        # Local aliases reset on context change, but global aliases still work
        result = resolve_name_candidate_by_rule(candidates[0], known)
        assert result is not None

    def test_fuzzy_match_with_long_dash(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 スーズーキータロー\n"
            "#9876543210 タナカハナコ\n"
            "スズキタロとタナカハナコ 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        known = {"1234567890", "9876543210"}
        result = resolve_name_candidate_by_rule(candidates[0], known)
        # "スーズーキータロー" (alias) vs "スズキタロ" (candidate name)
        # loose: both become "スズキタロ" (5 chars, meets min len)
        assert result is not None

    def test_same_inquiry_both_names(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#1234567890 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        candidates = extract_name_room_candidates(text)
        assert len(candidates) == 1
        known = {"1234567890"}
        result = resolve_name_candidate_by_rule(candidates[0], known)
        # Both names resolve to same inquiry -> None
        assert result is None
