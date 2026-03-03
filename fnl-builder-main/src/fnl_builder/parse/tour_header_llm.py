"""Tour header extraction with rule-based + LLM fallback chain."""
from __future__ import annotations

from fnl_builder.llm.adapter import LLMAdapter, NullAdapter
from fnl_builder.parse.tour_header import build_header_excerpt, extract_tour_header_rule
from fnl_builder.shared.types import Issue, TourHeaderData


def extract_tour_header(
    rl_text: str,
    llm: LLMAdapter,
    issues: list[Issue],
) -> TourHeaderData:
    """Extract tour header using rule-based approach with LLM fallback.

    1. Try rule-based extraction first.
    2. If rule-based fails and LLM is available, try LLM extraction.
    3. On any failure, return ``TourHeaderData.empty()``.
    """
    # --- Rule-based ---
    rule_result = extract_tour_header_rule(rl_text)
    if rule_result is not None:
        return rule_result

    # --- LLM fallback ---
    if isinstance(llm, NullAdapter):
        return TourHeaderData.empty()

    excerpt = build_header_excerpt(rl_text)
    if not excerpt:
        return TourHeaderData.empty()

    try:
        llm_result = llm.extract_tour_header(excerpt)
    except Exception as exc:
        issues.append(
            Issue(
                level="warning",
                code="tour_header_llm_failed",
                message=f"Tour header LLM extraction failed: {exc}",
            )
        )
        return TourHeaderData.empty()

    if llm_result is not None:
        return llm_result

    return TourHeaderData.empty()
