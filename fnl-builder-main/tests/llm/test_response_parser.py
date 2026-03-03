"""Tests for LLM response JSON parsing."""
from __future__ import annotations

import json

import pytest

from fnl_builder.llm.response_parser import parse_llm_response
from fnl_builder.shared.types import Category, Phase


def _make_item(**overrides: object) -> dict[str, object]:
    """Build a valid raw item dict with sensible defaults."""
    base: dict[str, object] = {
        "category": "medical_health",
        "phase": "on_tour",
        "summary": "Wheelchair needed",
        "handoff_text": "Please arrange wheelchair",
        "explicitness": "explicit",
        "urgency": "high",
        "confidence": 0.95,
        "severity": "warning",
        "caution_reason": "",
        "evidence_match": True,
        "evidence": {"page": 3, "quote": "車椅子が必要です"},
    }
    base.update(overrides)
    return base


class TestParseObjectFormat:
    def test_single_item(self) -> None:
        data = json.dumps({"items": [_make_item()]})
        result = parse_llm_response(data)
        assert len(result) == 1
        item = result[0]
        assert item.category == Category.MEDICAL
        assert item.phase == Phase.ON_TOUR
        assert item.confidence == 0.95
        assert item.summary == "Wheelchair needed"
        assert item.handoff_text == "Please arrange wheelchair"
        assert item.evidence_quote == "車椅子が必要です"
        assert item.evidence_page == 3

    def test_multiple_items(self) -> None:
        items = [
            _make_item(category="dietary", phase="meal_time"),
            _make_item(category="vip_sensitive", phase="hotel_stay"),
        ]
        data = json.dumps({"items": items})
        result = parse_llm_response(data)
        assert len(result) == 2
        assert result[0].category == Category.MEAL
        assert result[0].phase == Phase.MEAL_TIME
        assert result[1].category == Category.VIP_SENSITIVE
        assert result[1].phase == Phase.HOTEL_STAY

    def test_empty_items(self) -> None:
        data = json.dumps({"items": []})
        result = parse_llm_response(data)
        assert result == []


class TestParseArrayFormat:
    def test_bare_array(self) -> None:
        data = json.dumps([_make_item()])
        result = parse_llm_response(data)
        assert len(result) == 1
        assert result[0].category == Category.MEDICAL


class TestCategoryMapping:
    @pytest.mark.parametrize(
        ("schema_cat", "expected"),
        [
            ("medical_health", Category.MEDICAL),
            ("dietary", Category.MEAL),
            ("mobility_accessibility", Category.MOBILITY),
            ("vip_sensitive", Category.VIP_SENSITIVE),
            ("accommodation_room", Category.OTHER),
            ("grouping_companion", Category.OTHER),
            ("schedule_change_separation", Category.OTHER),
            ("documents_immigration", Category.OTHER),
            ("communication_language", Category.OTHER),
            ("baggage_equipment", Category.OTHER),
            ("other", Category.OTHER),
        ],
    )
    def test_category_mapping(self, schema_cat: str, expected: Category) -> None:
        data = json.dumps({"items": [_make_item(category=schema_cat)]})
        result = parse_llm_response(data)
        assert len(result) == 1
        assert result[0].category == expected


class TestPhaseMapping:
    @pytest.mark.parametrize(
        ("schema_phase", "expected"),
        [
            ("pre_departure", Phase.PRE_DEPARTURE),
            ("departure_airport", Phase.DEPARTURE_AIRPORT),
            ("flight", Phase.FLIGHT),
            ("arrival_airport", Phase.ARRIVAL_AIRPORT),
            ("transfer", Phase.TRANSFER),
            ("on_tour", Phase.ON_TOUR),
            ("hotel_stay", Phase.HOTEL_STAY),
            ("meal_time", Phase.MEAL_TIME),
            ("free_time_optional", Phase.FREE_TIME_OPTIONAL),
            ("return_trip", Phase.RETURN_TRIP),
            ("unknown", Phase.UNKNOWN),
        ],
    )
    def test_phase_mapping(self, schema_phase: str, expected: Phase) -> None:
        data = json.dumps({"items": [_make_item(phase=schema_phase)]})
        result = parse_llm_response(data)
        assert len(result) == 1
        assert result[0].phase == expected


class TestSkipInvalid:
    def test_unknown_category_skipped(self) -> None:
        data = json.dumps({"items": [_make_item(category="nonexistent")]})
        result = parse_llm_response(data)
        assert result == []

    def test_unknown_phase_skipped(self) -> None:
        data = json.dumps({"items": [_make_item(phase="nonexistent")]})
        result = parse_llm_response(data)
        assert result == []

    def test_non_dict_item_skipped(self) -> None:
        data = json.dumps({"items": ["not a dict", _make_item()]})
        result = parse_llm_response(data)
        assert len(result) == 1

    def test_mixed_valid_invalid(self) -> None:
        items = [
            _make_item(),
            _make_item(category="bogus"),
            _make_item(phase="bogus"),
            _make_item(category="dietary", phase="flight"),
        ]
        data = json.dumps({"items": items})
        result = parse_llm_response(data)
        assert len(result) == 2


class TestEdgeCases:
    def test_null_handoff_text(self) -> None:
        data = json.dumps({"items": [_make_item(handoff_text=None)]})
        result = parse_llm_response(data)
        assert result[0].handoff_text == ""

    def test_null_evidence_page(self) -> None:
        data = json.dumps(
            {"items": [_make_item(evidence={"page": None, "quote": "text"})]}
        )
        result = parse_llm_response(data)
        assert result[0].evidence_page is None
        assert result[0].evidence_quote == "text"

    def test_missing_evidence(self) -> None:
        item = _make_item()
        del item["evidence"]  # type: ignore[arg-type]
        data = json.dumps({"items": [item]})
        result = parse_llm_response(data)
        assert result[0].evidence_quote == ""
        assert result[0].evidence_page is None

    def test_who_id_defaults_empty(self) -> None:
        data = json.dumps({"items": [_make_item()]})
        result = parse_llm_response(data)
        assert result[0].who_id == ""

    def test_who_id_from_response(self) -> None:
        data = json.dumps({"items": [_make_item(who_id="0067621009-001")]})
        result = parse_llm_response(data)
        assert result[0].who_id == "0067621009-001"

    def test_who_id_invalid_format_falls_back(self) -> None:
        data = json.dumps({"items": [_make_item(who_id="invalid")]})
        result = parse_llm_response(data)
        assert result[0].who_id == ""

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            parse_llm_response("not json")

    def test_missing_items_key_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'items'"):
            parse_llm_response('{"data": []}')

    def test_non_list_items_raises(self) -> None:
        with pytest.raises(ValueError, match="missing 'items'"):
            parse_llm_response('{"items": "not a list"}')
