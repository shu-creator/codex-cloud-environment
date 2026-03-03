"""Tests for shared text utilities."""
from __future__ import annotations

from fnl_builder.shared.text import collapse_ws, contains_any, normalize_inquiry_main, safe_float


class TestCollapseWs:
    def test_multiple_spaces(self) -> None:
        assert collapse_ws("a   b") == "a b"

    def test_tabs_and_newlines(self) -> None:
        assert collapse_ws("a\t\nb") == "a b"

    def test_leading_trailing(self) -> None:
        assert collapse_ws("  hello  ") == "hello"

    def test_empty(self) -> None:
        assert collapse_ws("") == ""

    def test_mixed(self) -> None:
        assert collapse_ws("  a  b\tc  ") == "a b c"


class TestContainsAny:
    def test_hit(self) -> None:
        assert contains_any("甲殻類アレルギー", ("アレルギー", "食事制限")) is True

    def test_miss(self) -> None:
        assert contains_any("一般連絡", ("アレルギー", "食事制限")) is False

    def test_empty_keywords(self) -> None:
        assert contains_any("anything", ()) is False

    def test_empty_text(self) -> None:
        assert contains_any("", ("keyword",)) is False


class TestNormalizeInquiryMain:
    def test_strip_leading_zeros(self) -> None:
        assert normalize_inquiry_main("0067621009") == "67621009"

    def test_no_leading_zeros(self) -> None:
        assert normalize_inquiry_main("12345") == "12345"

    def test_all_zeros(self) -> None:
        assert normalize_inquiry_main("000") == "0"

    def test_single_zero(self) -> None:
        assert normalize_inquiry_main("0") == "0"


class TestSafeFloat:
    def test_int(self) -> None:
        assert safe_float(42) == 42.0

    def test_float(self) -> None:
        assert safe_float(3.14) == 3.14

    def test_str_number(self) -> None:
        assert safe_float("0.85") == 0.85

    def test_str_invalid(self) -> None:
        assert safe_float("abc") is None

    def test_bool_returns_none(self) -> None:
        assert safe_float(True) is None
        assert safe_float(False) is None

    def test_empty_string(self) -> None:
        assert safe_float("") is None
