from __future__ import annotations

from fnl_builder.parse.tour_header import (
    build_header_excerpt,
    extract_tour_header_rule,
    normalize_tour_header_candidate,
)


class TestExtractTourHeaderRule:
    def test_extracts_tour_ref_from_course_date_line(self) -> None:
        text = "E417Z 26-10-27 ～26-11-05\nsome content"
        result = extract_tour_header_rule(text)
        assert result is not None
        assert result.tour_ref == "E417Z 1027"

    def test_extracts_tour_name(self) -> None:
        text = """E417Z 26-10-27 ～26-11-05
E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS"""
        result = extract_tour_header_rule(text)
        assert result is not None
        assert result.tour_ref == "E417Z 1027"
        assert result.tour_name == "E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS"
        assert result.confidence == 0.95

    def test_returns_none_when_no_header(self) -> None:
        text = "random text without header info"
        result = extract_tour_header_rule(text)
        assert result is None

    def test_tour_name_only_lower_confidence(self) -> None:
        text = "E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS"
        result = extract_tour_header_rule(text)
        assert result is not None
        assert result.tour_ref is None
        assert result.confidence == 0.72


class TestBuildHeaderExcerpt:
    def test_keeps_tour_name_stops_at_guest_table(self) -> None:
        text = """ROOMING LIST
TOUR NAME E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS
No                  N     A    M         E             年齢       国籍       問合せNo
1 MR. HANKYU TARO 0067368202-001"""
        excerpt = build_header_excerpt(text)
        assert "TOUR NAME E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS" in excerpt
        assert "MR. HANKYU TARO" not in excerpt

    def test_does_not_stop_on_note_prefix(self) -> None:
        text = """ROOMING LIST
NOTE: operating carrier notice
TOUR NAME E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS
No                  N     A    M         E             年齢       国籍       問合せNo
1 MR. HANKYU TARO 0067368202-001"""
        excerpt = build_header_excerpt(text)
        assert "TOUR NAME E417 HEI OSA TRAPICS SPECIAL ITALY 10DAYS" in excerpt
        assert "MR. HANKYU TARO" not in excerpt

    def test_empty_text(self) -> None:
        assert build_header_excerpt("") == ""


class TestNormalizeTourHeaderCandidate:
    def test_valid_candidate(self) -> None:
        candidate = {"tour_ref": "E417Z 1027", "tour_name": "ITALY TOUR 10DAYS", "confidence": 0.92}
        result = normalize_tour_header_candidate(candidate)
        assert result is not None
        assert result.tour_ref == "E417Z 1027"
        assert result.tour_name == "ITALY TOUR 10DAYS"
        assert result.confidence == 0.92

    def test_invalid_tour_ref_dropped(self) -> None:
        candidate = {"tour_ref": "INVALID", "tour_name": "VALID NAME", "confidence": 0.9}
        result = normalize_tour_header_candidate(candidate)
        assert result is not None
        assert result.tour_ref is None
        assert result.tour_name == "VALID NAME"

    def test_no_confidence_returns_none(self) -> None:
        candidate = {"tour_ref": "E417Z 1027", "tour_name": "NAME"}
        result = normalize_tour_header_candidate(candidate)
        assert result is None

    def test_out_of_range_confidence_returns_none(self) -> None:
        candidate = {"tour_ref": "E417Z 1027", "tour_name": "NAME", "confidence": 1.5}
        result = normalize_tour_header_candidate(candidate)
        assert result is None

    def test_boolean_confidence_returns_none(self) -> None:
        candidate = {"tour_ref": "E417Z 1027", "tour_name": "NAME", "confidence": True}
        result = normalize_tour_header_candidate(candidate)
        assert result is None

    def test_empty_candidate_returns_none(self) -> None:
        candidate = {"tour_ref": None, "tour_name": None, "confidence": 0.9}
        result = normalize_tour_header_candidate(candidate)
        assert result is None
