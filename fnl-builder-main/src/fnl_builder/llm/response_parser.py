"""Parse LLM JSON response into typed LLMItem list."""
from __future__ import annotations

import json
import re

from fnl_builder.shared.types import Category, LLMItem, Phase

_WHO_ID_RE = re.compile(r"^\d{7,10}-\d{3}$")

# Map schema category values to Category StrEnum.
_CATEGORY_MAP: dict[str, Category] = {
    "medical_health": Category.MEDICAL,
    "dietary": Category.MEAL,
    "mobility_accessibility": Category.MOBILITY,
    "accommodation_room": Category.OTHER,
    "grouping_companion": Category.OTHER,
    "vip_sensitive": Category.VIP_SENSITIVE,
    "schedule_change_separation": Category.OTHER,
    "documents_immigration": Category.OTHER,
    "communication_language": Category.OTHER,
    "baggage_equipment": Category.OTHER,
    "other": Category.OTHER,
}

# Map schema phase values to Phase StrEnum.
_PHASE_MAP: dict[str, Phase] = {
    "pre_departure": Phase.PRE_DEPARTURE,
    "departure_airport": Phase.DEPARTURE_AIRPORT,
    "flight": Phase.FLIGHT,
    "arrival_airport": Phase.ARRIVAL_AIRPORT,
    "transfer": Phase.TRANSFER,
    "on_tour": Phase.ON_TOUR,
    "hotel_stay": Phase.HOTEL_STAY,
    "meal_time": Phase.MEAL_TIME,
    "free_time_optional": Phase.FREE_TIME_OPTIONAL,
    "return_trip": Phase.RETURN_TRIP,
    "unknown": Phase.UNKNOWN,
}


def parse_llm_response(response_json: str) -> list[LLMItem]:
    """Parse a JSON response string into a list of LLMItem.

    Accepts both ``{"items": [...]}`` and bare ``[...]`` formats.
    Items with unknown category or phase values are silently skipped.
    """
    parsed = json.loads(response_json)
    if isinstance(parsed, dict):
        items_raw = parsed.get("items")
        if not isinstance(items_raw, list):
            raise ValueError("LLM response missing 'items' array")
    elif isinstance(parsed, list):
        items_raw = parsed
    else:
        raise ValueError("LLM response is not a list or object")

    items: list[LLMItem] = []
    for raw in items_raw:
        if not isinstance(raw, dict):
            continue
        category = _CATEGORY_MAP.get(raw.get("category", ""))
        phase = _PHASE_MAP.get(raw.get("phase", ""))
        if category is None or phase is None:
            continue

        evidence = raw.get("evidence", {})
        if not isinstance(evidence, dict):
            evidence = {}

        items.append(
            LLMItem(
                category=category,
                who_id=raw.get("who_id", "") if _WHO_ID_RE.match(raw.get("who_id", "")) else "",
                confidence=float(raw.get("confidence", 0.0)),
                phase=phase,
                handoff_text=raw.get("handoff_text") or "",
                evidence_quote=evidence.get("quote", "") if evidence else "",
                summary=raw.get("summary", ""),
                evidence_page=evidence.get("page") if evidence else None,
            )
        )
    return items
