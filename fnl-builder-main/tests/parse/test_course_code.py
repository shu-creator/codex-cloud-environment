from __future__ import annotations

from fnl_builder.parse.course_code import (
    _is_valid_course_code,
    _normalize_candidate,
    _normalize_text,
    extract_course_code,
    find_course_codes,
)


class TestFindCourseCodes:
    def test_empty_string_returns_empty_list(self) -> None:
        assert find_course_codes("") == []

    def test_text_without_marker_returns_empty_list(self) -> None:
        assert find_course_codes("E417 出発日...") == []

    def test_single_code(self) -> None:
        text = "コースNO：E417 出発日..."
        assert find_course_codes(text) == ["E417"]

    def test_multiple_codes(self) -> None:
        text = "コースNO:E417 出発日... コースNO：EH420 帰着日..."
        assert find_course_codes(text) == ["E417", "EH420"]

    def test_window_too_short_to_capture_code(self) -> None:
        assert find_course_codes("コースNO：E417 出発日...", window=1) == []

    def test_q_series_code(self) -> None:
        assert find_course_codes("コースNO：AQ0001 出発日...") == ["AQ0001"]

    def test_deduplicates_repeated_code(self) -> None:
        text = "コースNO：E417 出発日... コースNO：E417 帰着日..."
        assert find_course_codes(text) == ["E417"]


class TestExtractCourseCode:
    def test_zero_results_returns_none(self) -> None:
        assert extract_course_code("marker なし") is None

    def test_one_result_returns_code(self) -> None:
        assert extract_course_code("コースNO：E417 出発日...") == "E417"

    def test_two_or_more_results_returns_none(self) -> None:
        text = "コースNO：E417 出発日... コースNO：EH420 帰着日..."
        assert extract_course_code(text) is None


class TestIsValidCourseCode:
    def test_valid_q_series(self) -> None:
        assert _is_valid_course_code("AQ0001")

    def test_valid_standard(self) -> None:
        assert _is_valid_course_code("E417")
        assert _is_valid_course_code("EH420")
        assert _is_valid_course_code("E417Z")

    def test_invalid_too_short(self) -> None:
        assert not _is_valid_course_code("A")
        assert not _is_valid_course_code("AQ1")

    def test_invalid_too_long(self) -> None:
        assert not _is_valid_course_code("AAA123")


class TestNormalizeText:
    def test_nfkc_normalization_full_width(self) -> None:
        assert _normalize_text("Ｅ４１７") == "E417"

    def test_uppercases_ascii_letters(self) -> None:
        assert _normalize_text("e417") == "E417"


class TestNormalizeCandidate:
    def test_strips_whitespace(self) -> None:
        assert _normalize_candidate("E 417") == "E417"
