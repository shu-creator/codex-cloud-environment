"""Unit tests for FNL shared/check parsing state machine."""
from __future__ import annotations

from dataclasses import dataclass, field

from fnl_builder.parse.messagelist_fnl import (
    consume_fnl_shared_line,
    consume_non_action_fnl_check_line,
    flush_fnl_shared_block,
    has_fnl_external_action,
    is_fnl_check_line,
    is_fnl_shared_end_line,
    is_fnl_shared_start_line,
    normalize_fnl_shared_line,
    resolve_pending_fnl_check_line,
    sanitize_fnl_shared_lines,
    start_fnl_shared_block,
    strip_internal_signature_suffix,
)


@dataclass
class _StubResult:
    fnl_check_required_by_guest: dict[tuple[str, str], int] = field(default_factory=dict)
    fnl_shared_meta_stripped_count: int = 0


@dataclass
class _StubState:
    current_inquiry: str | None = None
    current_guest_no: str | None = None
    is_csv_like: bool = False
    fnl_shared_active: bool = False
    fnl_shared_lines: list[str] = field(default_factory=list)
    fnl_shared_inquiry: str | None = None
    fnl_shared_guest_no: str | None = None
    pending_fnl_check_inquiry: str | None = None
    pending_fnl_check_guest_no: str | None = None


# --- is_fnl_check_line ---

class TestIsFnlCheckLine:
    def test_fnl_chk(self) -> None:
        assert is_fnl_check_line("FNL時CHK: 対応依頼") is True

    def test_fnl_check(self) -> None:
        assert is_fnl_check_line("FNL時チェック: 確認事項") is True

    def test_fnl_team(self) -> None:
        assert is_fnl_check_line("FNLチームさんへ 連絡") is True

    def test_fnl_team_no_san(self) -> None:
        assert is_fnl_check_line("FNLチームへ 確認") is True

    def test_fnl_check_plz(self) -> None:
        assert is_fnl_check_line("FNLチェックPLZ 内容") is True

    def test_non_fnl(self) -> None:
        assert is_fnl_check_line("一般連絡事項") is False

    def test_empty(self) -> None:
        assert is_fnl_check_line("") is False


# --- has_fnl_external_action ---

class TestHasFnlExternalAction:
    def test_haichi(self) -> None:
        assert has_fnl_external_action("ホテルに手配依頼") is True

    def test_kyoyu(self) -> None:
        assert has_fnl_external_action("現地ガイドに共有") is True

    def test_hotel(self) -> None:
        assert has_fnl_external_action("ホテルへ連絡") is True

    def test_no_action(self) -> None:
        assert has_fnl_external_action("確認しておく") is False

    def test_empty(self) -> None:
        assert has_fnl_external_action("") is False


# --- strip_internal_signature_suffix ---

class TestStripInternalSignatureSuffix:
    def test_standard_signature(self) -> None:
        text = "連絡事項 2025/02/11 10:20:30 東京営業所 山田太郎"
        result, removed = strip_internal_signature_suffix(text)
        assert result == "連絡事項"
        assert removed is True

    def test_compact_signature(self) -> None:
        text = "テキスト 2025-01-1510:20:30センター田中"
        result, removed = strip_internal_signature_suffix(text)
        assert result == "テキスト"
        assert removed is True

    def test_masked_signature(self) -> None:
        text = "テキスト 東京営業所 〇〇"
        result, removed = strip_internal_signature_suffix(text)
        assert result == "テキスト"
        assert removed is True

    def test_sama_exception(self) -> None:
        text = "連絡事項 2025/02/11 10:20:30 東京営業所 山田様"
        result, removed = strip_internal_signature_suffix(text)
        assert result == text
        assert removed is False

    def test_no_signature(self) -> None:
        text = "普通のテキスト"
        result, removed = strip_internal_signature_suffix(text)
        assert result == text
        assert removed is False

    def test_empty(self) -> None:
        result, removed = strip_internal_signature_suffix("")
        assert result == ""
        assert removed is False


# --- is_fnl_shared_start_line ---

class TestIsFnlSharedStartLine:
    def test_standard(self) -> None:
        assert is_fnl_shared_start_line("FNL時共有PLZ") is True

    def test_katakana(self) -> None:
        assert is_fnl_shared_start_line("ファイナル時共有PLZ") is True

    def test_kisai(self) -> None:
        assert is_fnl_shared_start_line("FNL時記載PLZ") is True

    def test_non_match(self) -> None:
        assert is_fnl_shared_start_line("一般テキスト") is False


# --- is_fnl_shared_end_line ---

class TestIsFnlSharedEndLine:
    def test_date_prefix(self) -> None:
        state = _StubState()
        assert is_fnl_shared_end_line("03-06 OP申込", state) is True

    def test_inquiry_pdf(self) -> None:
        state = _StubState()
        assert is_fnl_shared_end_line("0067621009-001 山田太郎", state) is True

    def test_guest_id(self) -> None:
        state = _StubState()
        assert is_fnl_shared_end_line("顧客 0067621009-001", state) is True

    def test_csv_inquiry(self) -> None:
        state = _StubState(is_csv_like=True)
        assert is_fnl_shared_end_line("[問合せNO: 0067621009] 内容", state) is True

    def test_csv_inquiry_not_csv_mode(self) -> None:
        state = _StubState(is_csv_like=False)
        assert is_fnl_shared_end_line("[問合せNO: 0067621009] 内容", state) is False

    def test_normal_text(self) -> None:
        state = _StubState()
        assert is_fnl_shared_end_line("普通のテキスト", state) is False

    def test_empty(self) -> None:
        state = _StubState()
        assert is_fnl_shared_end_line("", state) is False


# --- normalize_fnl_shared_line ---

class TestNormalizeFnlSharedLine:
    def test_strips_header(self) -> None:
        result = _StubResult()
        assert normalize_fnl_shared_line("【後方メモ】: 内容テキスト", result) == "内容テキスト"

    def test_fnl_header_only(self) -> None:
        result = _StubResult()
        assert normalize_fnl_shared_line("FNL時共有PLZ", result) == ""

    def test_strips_signature_and_counts(self) -> None:
        result = _StubResult()
        out = normalize_fnl_shared_line("内容 2025/02/11 10:20:30 東京営業所 山田太郎", result)
        assert out == "内容"
        assert result.fnl_shared_meta_stripped_count == 1

    def test_empty_line(self) -> None:
        result = _StubResult()
        assert normalize_fnl_shared_line("", result) == ""


# --- sanitize_fnl_shared_lines ---

class TestSanitizeFnlSharedLines:
    def test_dedup_adjacent(self) -> None:
        result = _StubResult()
        lines = ["テキストA", "テキストA", "テキストB"]
        assert sanitize_fnl_shared_lines(lines, result) == ["テキストA", "テキストB"]

    def test_empty_lines_removed(self) -> None:
        result = _StubResult()
        lines = ["テキスト", "", "FNL時共有PLZ"]
        assert sanitize_fnl_shared_lines(lines, result) == ["テキスト"]


# --- consume_non_action_fnl_check_line ---

class TestConsumeNonActionFnlCheckLine:
    def test_non_fnl_line(self) -> None:
        state = _StubState(current_inquiry="123")
        assert consume_non_action_fnl_check_line("一般テキスト", state) is False
        assert state.pending_fnl_check_inquiry is None

    def test_fnl_check_with_action(self) -> None:
        state = _StubState(current_inquiry="123")
        assert consume_non_action_fnl_check_line("FNL時CHK: ホテルに手配", state) is True
        assert state.pending_fnl_check_inquiry is None

    def test_fnl_check_without_action(self) -> None:
        state = _StubState(current_inquiry="123", current_guest_no="001")
        assert consume_non_action_fnl_check_line("FNL時CHK: 確認する", state) is True
        assert state.pending_fnl_check_inquiry == "123"
        assert state.pending_fnl_check_guest_no == "001"


# --- resolve_pending_fnl_check_line ---

class TestResolvePendingFnlCheckLine:
    def test_no_pending(self) -> None:
        result = _StubResult()
        state = _StubState()
        resolve_pending_fnl_check_line("any text", result, state)
        assert result.fnl_check_required_by_guest == {}

    def test_next_line_has_action_clears_pending(self) -> None:
        result = _StubResult()
        state = _StubState(pending_fnl_check_inquiry="123", pending_fnl_check_guest_no="001")
        resolve_pending_fnl_check_line("ホテルに手配依頼", result, state)
        assert state.pending_fnl_check_inquiry is None
        assert result.fnl_check_required_by_guest == {}

    def test_next_line_no_action_records(self) -> None:
        result = _StubResult()
        state = _StubState(pending_fnl_check_inquiry="123", pending_fnl_check_guest_no="001")
        resolve_pending_fnl_check_line("別の内容", result, state)
        assert result.fnl_check_required_by_guest == {("123", "001"): 1}
        assert state.pending_fnl_check_inquiry is None


# --- start_fnl_shared_block ---

class TestStartFnlSharedBlock:
    def test_sets_state(self) -> None:
        state = _StubState(current_inquiry="456", current_guest_no="002")
        start_fnl_shared_block(state, "FNL時共有PLZ 内容")
        assert state.fnl_shared_active is True
        assert state.fnl_shared_lines == ["FNL時共有PLZ 内容"]
        assert state.fnl_shared_inquiry == "456"
        assert state.fnl_shared_guest_no == "002"


# --- flush_fnl_shared_block ---

class TestFlushFnlSharedBlock:
    def test_flush_produces_remark(self) -> None:
        result = _StubResult()
        state = _StubState(
            fnl_shared_active=True,
            fnl_shared_inquiry="456",
            fnl_shared_guest_no="002",
            fnl_shared_lines=["テスト内容"],
        )
        stored: list[tuple[str, str | None, str]] = []
        flush_fnl_shared_block(result, state, store_remark=lambda i, g, r: stored.append((i, g, r)))
        assert len(stored) == 1
        assert stored[0][0] == "456"
        assert stored[0][1] == "002"
        assert "[fnl_shared_plz]" in stored[0][2]
        assert state.fnl_shared_active is False

    def test_flush_no_inquiry_resets(self) -> None:
        result = _StubResult()
        state = _StubState(fnl_shared_active=True, fnl_shared_inquiry=None)
        stored: list[tuple[str, str | None, str]] = []
        flush_fnl_shared_block(result, state, store_remark=lambda i, g, r: stored.append((i, g, r)))
        assert len(stored) == 0
        assert state.fnl_shared_active is False

    def test_flush_empty_lines_resets(self) -> None:
        result = _StubResult()
        state = _StubState(
            fnl_shared_active=True,
            fnl_shared_inquiry="456",
            fnl_shared_lines=["FNL時共有PLZ"],
        )
        stored: list[tuple[str, str | None, str]] = []
        flush_fnl_shared_block(result, state, store_remark=lambda i, g, r: stored.append((i, g, r)))
        assert len(stored) == 0


# --- consume_fnl_shared_line ---

class TestConsumeFnlSharedLine:
    def test_not_active(self) -> None:
        result = _StubResult()
        state = _StubState(fnl_shared_active=False)
        stored: list[tuple[str, str | None, str]] = []
        assert consume_fnl_shared_line("text", result, state, store_remark=lambda i, g, r: stored.append((i, g, r))) is False

    def test_end_line_flushes(self) -> None:
        result = _StubResult()
        state = _StubState(
            fnl_shared_active=True,
            fnl_shared_inquiry="456",
            fnl_shared_lines=["内容テキスト"],
        )
        stored: list[tuple[str, str | None, str]] = []
        consumed = consume_fnl_shared_line(
            "03-06 次のセクション", result, state,
            store_remark=lambda i, g, r: stored.append((i, g, r)),
        )
        assert consumed is False
        assert len(stored) == 1

    def test_normal_line_appended(self) -> None:
        result = _StubResult()
        state = _StubState(
            fnl_shared_active=True,
            fnl_shared_inquiry="456",
            fnl_shared_lines=["最初の行"],
        )
        stored: list[tuple[str, str | None, str]] = []
        consumed = consume_fnl_shared_line(
            "追加テキスト", result, state,
            store_remark=lambda i, g, r: stored.append((i, g, r)),
        )
        assert consumed is True
        assert "追加テキスト" in state.fnl_shared_lines
