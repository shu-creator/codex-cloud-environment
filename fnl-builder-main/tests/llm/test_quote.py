"""Tests for evidence quote candidate extraction."""
from __future__ import annotations

from fnl_builder.llm.quote import (
    _candidate_lines,
    _is_header_line,
    _slice_quote,
    find_phrase_page,
    select_quote_candidates,
)


class TestFindPhrasePage:
    def test_found(self) -> None:
        pages = [(1, "hello"), (2, "world")]
        assert find_phrase_page("world", pages) == 2

    def test_not_found(self) -> None:
        pages = [(1, "hello")]
        assert find_phrase_page("missing", pages) is None

    def test_empty_pages(self) -> None:
        assert find_phrase_page("x", []) is None


class TestIsHeaderLine:
    def test_date_line(self) -> None:
        assert _is_header_line("12-01-26 departure") is True

    def test_time_line(self) -> None:
        assert _is_header_line("Meeting at 09:30:00") is True

    def test_no_name_header(self) -> None:
        assert _is_header_line("NO  NAME  PASSPORT") is True

    def test_spaced_name(self) -> None:
        assert _is_header_line("N A M E column") is True

    def test_normal_line(self) -> None:
        assert _is_header_line("車椅子が必要です") is False


class TestSliceQuote:
    def test_short_text(self) -> None:
        assert _slice_quote("hello") == "hello"

    def test_long_text_truncated(self) -> None:
        long_text = "a" * 50
        result = _slice_quote(long_text)
        assert result is not None
        assert len(result) == 30

    def test_empty_returns_none(self) -> None:
        assert _slice_quote("") is None
        assert _slice_quote("  ") is None


class TestCandidateLines:
    def test_empty_text(self) -> None:
        assert _candidate_lines("") == []

    def test_header_only(self) -> None:
        assert _candidate_lines("NO  NAME  PASSPORT\n12-01-26 dep") == []

    def test_who_id_lines_prioritised(self) -> None:
        text = "Header line 1\nHeader line 2\n田中太郎 0067368202-001\n車椅子が必要\n佐藤花子 0067368202-002\n"
        lines = _candidate_lines(text)
        # who_id lines should appear first
        assert any("0067368202-001" in line for line in lines)

    def test_keyword_lines_included(self) -> None:
        text = "Line1\nLine2\nLine3\n特記事項: wheelchair\n"
        lines = _candidate_lines(text)
        assert any("特記事項" in line for line in lines)


class TestSelectQuoteCandidates:
    def test_basic(self) -> None:
        pages = [(1, "Header1\nHeader2\n田中太郎 0067368202-001\n車椅子が必要\n")]
        candidates = select_quote_candidates(pages)
        assert len(candidates) >= 1
        assert all(isinstance(c, tuple) and len(c) == 2 for c in candidates)

    def test_empty_pages(self) -> None:
        assert select_quote_candidates([]) == []

    def test_no_duplicates(self) -> None:
        pages = [(1, "Line1\nLine2\nContent line\n"), (1, "Line1\nLine2\nContent line\n")]
        candidates = select_quote_candidates(pages)
        seen = set()
        for c in candidates:
            assert c not in seen
            seen.add(c)

    def test_quote_must_exist_in_text(self) -> None:
        # All candidates must be findable in the original page text
        pages = [(1, "Header1\nHeader2\n田中太郎 0067368202-001\n車椅子が必要\n")]
        candidates = select_quote_candidates(pages)
        page_text = pages[0][1]
        for _, quote in candidates:
            assert quote in page_text
