from __future__ import annotations

import re

from fnl_builder.integrate.category import _RULE_LABEL_TO_CATEGORY
from fnl_builder.integrate.category import _parse_remark_category
from fnl_builder.integrate.category import _refine_category_by_content
from fnl_builder.shared.text import collapse_ws, contains_any
from fnl_builder.shared.types import Category, Issue, LLMItem, Phase

_VIP_LABEL_RE = re.compile(r"^\[\s*vip\s*\]", re.IGNORECASE)
_VIP_CONFIDENCE_THRESHOLD = 0.80
_VIP_TRAVEL_PHASES = {
    Phase.DEPARTURE_AIRPORT,
    Phase.FLIGHT,
    Phase.ARRIVAL_AIRPORT,
    Phase.TRANSFER,
    Phase.ON_TOUR,
    Phase.HOTEL_STAY,
    Phase.MEAL_TIME,
    Phase.FREE_TIME_OPTIONAL,
    Phase.RETURN_TRIP,
}
_VIP_NON_SHAREABLE_KEYWORDS = (
    "電話",
    "入電",
    "架電",
    "店頭",
    "カウンター",
    "窓口",
    "メール",
    "コールセンター",
    "社内",
    "営業担当",
    "オペレーション",
)
_VIP_TRAVEL_CONTEXT_KEYWORDS = (
    "現地",
    "ツアー中",
    "添乗員",
    "ガイド",
    "ホテル",
    "レストラン",
    "観光",
    "行程",
    "機内",
    "空港",
    "送迎",
    "チェックイン",
    "チェックアウト",
    "バス",
    "離団",
    "合流",
)
_VIP_RULE_KEYWORDS = ("重要顧客",)
_VIP_RELATION_PATTERNS = (
    re.compile(r"(?:弊社|当社)?\s*(?:取引先|提携先|関係会社)\s*(?:の)?\s*(?:役員|幹部)?"),
    re.compile(r"(?:取引先|提携先|関係会社)\s*(?:の)?\s*(?:役員|幹部)"),
    re.compile(r"(?:社長|担当者)\s*の?\s*知人"),
    re.compile(r"(?:役員|幹部)"),
)
_VIP_INTERNAL_CONTEXT_PATTERNS = (
    re.compile(r"(?:弊社|当社)"),
    re.compile(r"(?:社内|営業担当|担当者)"),
    re.compile(r"オペレーション(?:課|係|センター)?"),
)


def _is_vip_item(item: LLMItem) -> bool:
    return item.category == Category.VIP_SENSITIVE


def _is_shareable_vip_item(item: LLMItem) -> bool:
    if not _is_vip_item(item):
        return False
    if item.confidence < _VIP_CONFIDENCE_THRESHOLD:
        return False
    text = collapse_ws(f"{item.handoff_text} {item.evidence_quote}")
    if contains_any(text, _VIP_NON_SHAREABLE_KEYWORDS):
        return False
    if item.phase in _VIP_TRAVEL_PHASES:
        return True
    if item.phase == Phase.UNKNOWN and contains_any(text, _VIP_TRAVEL_CONTEXT_KEYWORDS):
        return True
    return False


def _detect_vip_action(text: str) -> str:
    if "アップグレード" in text:
        return "部屋アップグレード希望"
    if re.search(r"VIP\s*(?:待遇|対応)?", text, re.IGNORECASE):
        return "VIP対応希望"
    if "要配慮" in text or contains_any(text, ("問題行動", "トラブル", "揉め", "怒")):
        return "要配慮対応希望"
    return "要配慮対応希望"


def _generalize_vip_handoff_text(text: str) -> str:
    normalized = collapse_ws(text).strip("。")
    if not normalized:
        return ""
    for pattern in _VIP_RELATION_PATTERNS:
        normalized = pattern.sub("重要顧客", normalized)
    for pattern in _VIP_INTERNAL_CONTEXT_PATTERNS:
        normalized = pattern.sub("", normalized)
    normalized = collapse_ws(normalized).strip("。")
    action = _detect_vip_action(normalized)
    return f"重要顧客のため{action}"


def _is_vip_candidate_remark(remark: str) -> bool:
    normalized = collapse_ws(remark)
    if not normalized:
        return False
    if _VIP_LABEL_RE.match(normalized):
        return True
    if "VIP" in normalized.upper():
        return True
    return contains_any(normalized, _VIP_RULE_KEYWORDS)


def _is_related_to_vip_items(remark: str, guest_llm_items: list[LLMItem]) -> bool:
    normalized_remark = collapse_ws(remark)
    if not normalized_remark:
        return False
    if _is_vip_candidate_remark(normalized_remark):
        return True
    label, body = _parse_remark_category(normalized_remark)
    raw_label = (label or "other").lower()
    label_category = _RULE_LABEL_TO_CATEGORY.get(raw_label, "other")
    if label_category == "vip":
        return True
    if _refine_category_by_content(label_category, body or normalized_remark) == "vip":
        return True
    for item in guest_llm_items:
        if not _is_vip_item(item):
            continue
        source = collapse_ws(item.handoff_text or item.summary)
        if not source:
            continue
        if source in normalized_remark or normalized_remark in source:
            return True
        source_terms = [term for term in re.split(r"[ /／・･、。,]+", source) if len(term) >= 3]
        if any(term in normalized_remark for term in source_terms):
            return True
    return False


def _build_generalized_vip_remarks(guest_llm_items: list[LLMItem]) -> list[str]:
    generalized: list[str] = []
    for item in guest_llm_items:
        if not _is_shareable_vip_item(item):
            continue
        source_text = item.handoff_text or item.summary
        transformed = _generalize_vip_handoff_text(source_text)
        if not transformed:
            continue
        formatted = f"[vip] {transformed}"
        if formatted not in generalized:
            generalized.append(formatted)
    return generalized


def _resolve_vip_merge(
    candidate_remarks: list[str],
    guest_llm_items: list[LLMItem],
    *,
    issues: list[Issue],
) -> tuple[list[str], bool, list[str]]:
    if not any(_is_vip_item(item) for item in guest_llm_items):
        return candidate_remarks, False, []
    candidate_remarks_before_vip = list(candidate_remarks)
    try:
        generated_vip_remarks = _build_generalized_vip_remarks(guest_llm_items)
        filtered_candidate_remarks = [remark for remark in candidate_remarks if not _is_related_to_vip_items(remark, guest_llm_items)]
        return filtered_candidate_remarks, True, generated_vip_remarks
    except Exception:
        issues.append(
            Issue(
                level="warning",
                code="vip_generalize_fallback",
                message="VIP整形に失敗したため従来マージで継続しました。",
            )
        )
        safe_remarks = [remark for remark in candidate_remarks_before_vip if not _is_related_to_vip_items(remark, guest_llm_items)]
        return safe_remarks, False, []
