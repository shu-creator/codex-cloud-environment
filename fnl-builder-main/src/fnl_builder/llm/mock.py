"""Extended mock adapter for realistic LLM extraction testing."""
from __future__ import annotations

from typing import cast

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.quote import find_phrase_page, select_quote_candidates
from fnl_builder.parse.tour_header import extract_tour_header_rule
from fnl_builder.shared.types import Category, LLMItem, Phase, TourHeaderData

_REQUIRED_PHRASES: list[tuple[str, str, str, str]] = [
    (
        "medical_health",
        "pre_departure",
        "インシュリンの件",
        "医療対応が必要",
    ),
    (
        "schedule_change_separation",
        "pre_departure",
        "DEP日変更",
        "日程変更への対応が必要",
    ),
    (
        "baggage_equipment",
        "flight",
        "体温計（水銀式）",
        "特殊手荷物の対応が必要",
    ),
    (
        "other",
        "flight",
        "ハネムーンケーキ",
        "機内対応の共有が必要",
    ),
]

_SCHEMA_CATEGORY_TO_CATEGORY: dict[str, Category] = {
    "medical_health": Category.MEDICAL,
    "dietary": Category.MEAL,
    "mobility_accessibility": Category.MOBILITY,
    "accommodation_room": Category.OTHER,
    "schedule_change_separation": Category.OTHER,
    "baggage_equipment": Category.OTHER,
    "anniversary_celebration": Category.ANNIVERSARY,
    "repeat_customer": Category.REPEAT,
    "vip_or_sensitive_customer": Category.VIP_SENSITIVE,
    "documents_regulatory": Category.OTHER,
    "other": Category.OTHER,
}

_SCHEMA_PHASE_TO_PHASE: dict[str, Phase] = {
    "extract": Phase.EXTRACT,
    "rewrite": Phase.REWRITE,
    "pre_departure": Phase.PRE_DEPARTURE,
    "departure_airport": Phase.DEPARTURE_AIRPORT,
    "flight": Phase.FLIGHT,
    "arrival_airport": Phase.ARRIVAL_AIRPORT,
    "on_tour": Phase.ON_TOUR,
    "hotel": Phase.HOTEL_STAY,
    "meal": Phase.MEAL_TIME,
    "return_flight": Phase.RETURN_TRIP,
    "post_tour": Phase.UNKNOWN,
    "transfer": Phase.TRANSFER,
    "free_time": Phase.FREE_TIME_OPTIONAL,
}


def _select_quote(
    phrase: str,
    pages: list[object],
    *,
    item_index: int,
    fallback_candidates: list[tuple[int, str]],
) -> tuple[int | None, str]:
    """Find evidence quote for a mock item."""
    typed_pages = cast(list[tuple[int, str]], pages)
    page_no = find_phrase_page(phrase, typed_pages)
    if page_no is not None:
        return page_no, phrase

    if fallback_candidates:
        idx = item_index % len(fallback_candidates)
        return fallback_candidates[idx]

    return None, phrase


class FullMockAdapter:
    """Mock adapter that generates realistic LLM items from page content.

    Unlike the simple ``MockAdapter`` (which returns pre-built items),
    this adapter inspects page text to build evidence quotes and produces
    the 4 required phrases used for prompt regression testing.
    """

    def extract_remarks(
        self, text: str, pages: list[object], prompts: PromptConfig,
    ) -> list[LLMItem]:
        typed_pages = cast(list[tuple[int, str]], pages)
        fallback_candidates = select_quote_candidates(typed_pages)
        items: list[LLMItem] = []

        for item_index, (category_key, phase_key, phrase, summary) in enumerate(
            _REQUIRED_PHRASES,
        ):
            page_no, quote = _select_quote(
                phrase,
                pages,
                item_index=item_index,
                fallback_candidates=fallback_candidates,
            )
            category = _SCHEMA_CATEGORY_TO_CATEGORY.get(category_key, Category.OTHER)
            phase = _SCHEMA_PHASE_TO_PHASE.get(phase_key, Phase.ON_TOUR)
            items.append(
                LLMItem(
                    category=category,
                    who_id="",
                    confidence=0.7,
                    phase=phase,
                    handoff_text=summary,
                    evidence_quote=quote,
                    summary=summary,
                    evidence_page=page_no,
                )
            )

        return items

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        return extract_tour_header_rule(excerpt)

