"""Tests for LLM prompt loading and course-code resolution."""
from __future__ import annotations

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.prompt_loader import (
    _extract_course_number,
    _load_course_supplement,
    load_prompts,
    load_taxonomy,
)


class TestExtractCourseNumber:
    def test_simple_code(self) -> None:
        assert _extract_course_number("E417") == "417"

    def test_two_letter_prefix(self) -> None:
        assert _extract_course_number("EH417") == "417"

    def test_different_number(self) -> None:
        assert _extract_course_number("ET470") == "470"

    def test_no_digits(self) -> None:
        assert _extract_course_number("ABC") is None

    def test_single_digit(self) -> None:
        assert _extract_course_number("E5") == "5"

    def test_suffix_variant(self) -> None:
        assert _extract_course_number("E417Z") == "417"

    def test_two_letter_suffix(self) -> None:
        assert _extract_course_number("E417ZC") == "417"

    def test_three_letter_prefix(self) -> None:
        assert _extract_course_number("EXA417") == "417"

    def test_code_with_suffix_digits(self) -> None:
        assert _extract_course_number("EX417") == "417"


class TestLoadCourseSupplementReal:
    """Tests using real course files in the prompts/courses/ directory."""

    def test_known_course_417(self) -> None:
        result = _load_course_supplement(["E417"])
        assert "シェンゲン" in result
        assert "離団" in result

    def test_unknown_course_fallback(self) -> None:
        result = _load_course_supplement(["E999"])
        assert "コース固有の追加指示はありません" in result

    def test_empty_codes_fallback(self) -> None:
        result = _load_course_supplement([])
        assert "コース固有の追加指示はありません" in result

    def test_multiple_codes_same_number(self) -> None:
        result1 = _load_course_supplement(["E417"])
        result2 = _load_course_supplement(["E417", "EH417"])
        assert result1 == result2

    def test_mixed_known_unknown(self) -> None:
        result = _load_course_supplement(["E417", "E999"])
        assert "シェンゲン" in result
        assert "コース固有の追加指示はありません" not in result

    def test_suffix_code_resolves(self) -> None:
        result = _load_course_supplement(["E417Z"])
        assert "シェンゲン" in result


class TestLoadPrompts:
    def test_returns_prompt_config(self) -> None:
        config = load_prompts()
        assert isinstance(config, PromptConfig)

    def test_system_prompt_loaded(self) -> None:
        config = load_prompts()
        assert "FNL自動化" in config.system
        assert "System Prompt" in config.system

    def test_extract_base_loaded(self) -> None:
        config = load_prompts()
        assert "{{TAXONOMY_YAML}}" in config.extract_base
        assert "{{PAGES_TEXT}}" in config.extract_base
        assert "ML items schema" in config.extract_base

    def test_extract_base_no_duplicated_rules(self) -> None:
        """User prompt should not duplicate detailed rules from system prompt."""
        config = load_prompts()
        # These phrases belong in system prompt only
        assert "問答無用で捨てる" not in config.extract_base
        assert "推測抑制(同室)" not in config.extract_base
        assert "ランドオンリー抽出" not in config.extract_base
        assert "イレギュラー伝達事項" not in config.extract_base

    def test_default_course_supplement(self) -> None:
        config = load_prompts()
        assert "コース固有の追加指示はありません" in config.course_supplement

    def test_specific_course_supplement(self) -> None:
        config = load_prompts(["E417"])
        assert "シェンゲン" in config.course_supplement

    def test_with_none_course_codes(self) -> None:
        config = load_prompts(None)
        assert isinstance(config.course_supplement, str)


class TestLoadTaxonomy:
    def test_loads_yaml(self) -> None:
        text = load_taxonomy()
        assert "categories:" in text
        assert "phases:" in text

    def test_contains_all_categories(self) -> None:
        text = load_taxonomy()
        expected_ids = [
            "medical_health",
            "dietary",
            "mobility_accessibility",
            "accommodation_room",
            "grouping_companion",
            "vip_sensitive",
            "schedule_change_separation",
            "documents_immigration",
            "communication_language",
            "baggage_equipment",
            "other",
        ]
        for cat_id in expected_ids:
            assert cat_id in text, f"Missing category: {cat_id}"

    def test_contains_all_phases(self) -> None:
        text = load_taxonomy()
        expected_phases = [
            "pre_departure",
            "departure_airport",
            "flight",
            "arrival_airport",
            "transfer",
            "on_tour",
            "hotel_stay",
            "meal_time",
            "free_time_optional",
            "return_trip",
            "unknown",
        ]
        for phase_id in expected_phases:
            assert phase_id in text, f"Missing phase: {phase_id}"
