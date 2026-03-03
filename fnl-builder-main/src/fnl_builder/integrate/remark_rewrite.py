from __future__ import annotations

import re

from fnl_builder.integrate.category import _RULE_LABEL_TO_CATEGORY
from fnl_builder.integrate.category import _parse_remark_category
from fnl_builder.integrate.category import _refine_category_by_content
from fnl_builder.integrate.category import _relabel_remark
from fnl_builder.integrate.vip import _VIP_LABEL_RE
from fnl_builder.shared.text import collapse_ws
from fnl_builder.shared.types import Category, LLMItem, RewriteStats

_INTERNAL_SIGNATURE_SUFFIX_RE = re.compile(
    r"\s*(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"
    r"\s+\d{1,2}:\d{2}:\d{2}"
    r"\s+(?P<org>\S*(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション|ｶｳﾝﾀｰ|カウンター|ｾﾝﾀｰ)\S*)"
    r"\s+(?P<name>[A-Za-z一-龯ぁ-んァ-ヶー]{1,20}(?:\s+[A-Za-z一-龯ぁ-んァ-ヶー]{1,20}){0,2})\s*$"
)
_INTERNAL_SIGNATURE_COMPACT_SUFFIX_RE = re.compile(
    r"\s*(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"
    r"\s*\d{1,2}:\d{2}:\d{2}"
    r"(?P<org>\S*?(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション|ｶｳﾝﾀｰ|カウンター|ｾﾝﾀｰ))"
    r"(?P<name>[A-Za-z一-龯ぁ-んァ-ヶー〇○●◯]{1,20})\s*$"
)
_INTERNAL_SIGNATURE_MASKED_SUFFIX_RE = re.compile(
    r"\s+(?P<org>\S*(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション|仕入|ｶｳﾝﾀｰ|カウンター|ｾﾝﾀｰ)\S*)"
    r"\s+(?P<name>[〇○●◯]{1,4})\s*$"
)
_INTERNAL_SIGNATURE_SHORT_DATE_RE = re.compile(
    r"(?<!\d)\s*(?:\d{2}|(?:19|20)\d{2})[/-]\d{1,2}[/-]\d{1,2}"
    r"(?:\s*\d{1,2}:\d{2}(?::\d{2})?)?"
    r"\s*(?P<org>\S*?(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション|ｶｳﾝﾀｰ|カウンター|ｾﾝﾀｰ))"
    r"\s*(?P<name>[A-Za-z一-龯ぁ-んァ-ヶーｦ-ﾟ]{1,20})\s*$"
)
_FNL_SHARED_LABEL_RE = re.compile(
    r"^(?:\[\s*問合せ\s*NO:\s*\d{7,10}\]\s*)?\[\s*fnl_shared_plz\s*\]",
    re.IGNORECASE,
)
_MEDICAL_LABEL_KEYWORDS = (
    "medical",
    "medical_health",
    "dietary",
    "meal",
    "mobility",
    "mobility_accessibility",
)
_MEDICAL_CONFIDENCE_THRESHOLD = 0.80
_MEDICAL_CATEGORIES: set[Category] = {
    Category.MEDICAL,
    Category.MEAL,
    Category.MOBILITY,
}
_MEDICAL_REMARK_LABELS_BY_CATEGORY: dict[Category, tuple[str, ...]] = {
    Category.MEDICAL: ("medical", "medical_health"),
    Category.MEAL: ("meal", "dietary"),
    Category.MOBILITY: ("mobility", "mobility_accessibility"),
}
_MEDICAL_BODY_KEYWORDS = (
    "アレルギー",
    "ｱﾚﾙｷﾞｰ",
    "病人",
    "身体障害",
    "糖尿",
    "インシュリン",
    "車椅子",
    "車いす",
    "要配慮",
)
_MEDICAL_CATEGORY_STRINGS: frozenset[str] = frozenset(_MEDICAL_LABEL_KEYWORDS)
# Categories where rule remark is kept as supplement alongside LLM output.
# meal (allergy/dietary) is excluded — LLM summary is sufficient.
_MEDICAL_SUPPLEMENT_STRINGS: frozenset[str] = frozenset(("medical", "mobility"))
_INTERNAL_MEMO_PHRASE_RE = re.compile(
    r"[→※]?\s*(?:"
    r"営業へ回送済み?"
    r"|営業へ[^\s。]*連絡メモ[^\s。]*?(?:済み?|せず)"
    r"|【営業様?】"
    r"|(?:ｲﾗ|ｱﾅ|ﾚﾗ|イラ|アナ|レラ)済[み]?"
    r"|HC登録あり"
    r"|お伺い書待ち"
    r"|DEP先の為[^\s。]*せず"
    r"|連絡[ﾒメ][ﾓモ]送信せず"
    r")\s*[。]?\s*"
)


def _strip_internal_memo_phrases(text: str) -> str:
    result = _INTERNAL_MEMO_PHRASE_RE.sub("", text)
    return collapse_ws(result)


def _append_unique_remarks(base: list[str], additions: list[str]) -> list[str]:
    for remark in additions:
        if remark and remark not in base:
            base.append(remark)
    return base


def _is_fnl_shared_remark(remark: str) -> bool:
    return bool(_FNL_SHARED_LABEL_RE.match(collapse_ws(remark)))


def _sanitize_remarks_parts(remarks_parts: list[str]) -> list[str]:
    sanitized: list[str] = []
    for remark in remarks_parts:
        if not remark:
            continue
        cleaned = _strip_internal_signature_suffix(collapse_ws(remark))
        cleaned = _strip_internal_memo_phrases(cleaned)
        if cleaned:
            sanitized.append(cleaned)
    return _append_unique_remarks([], sanitized)


def _mergeable_llm_remarks(guest_llm_remarks: list[str], *, skip_vip_label: bool) -> list[str]:
    merged: list[str] = []
    for llm_remark in guest_llm_remarks:
        cleaned_llm = _strip_internal_signature_suffix(llm_remark)
        if not cleaned_llm:
            continue
        if skip_vip_label and _VIP_LABEL_RE.match(cleaned_llm):
            continue
        if cleaned_llm not in merged:
            merged.append(cleaned_llm)
    return merged


def _strip_internal_signature_suffix(text: str) -> str:
    source = text or ""
    for pattern in (
        _INTERNAL_SIGNATURE_SUFFIX_RE,
        _INTERNAL_SIGNATURE_COMPACT_SUFFIX_RE,
        _INTERNAL_SIGNATURE_MASKED_SUFFIX_RE,
        _INTERNAL_SIGNATURE_SHORT_DATE_RE,
    ):
        match = pattern.search(source)
        if not match:
            continue
        if "様" in match.group("name"):
            return source.strip()
        return source[: match.start()].strip()
    return source.strip()


def _is_medical_like_remark(remark: str) -> bool:
    label, body = _parse_remark_category(remark)
    label_text = label or ""
    body_text = body or collapse_ws(remark)
    if any(keyword in label_text for keyword in _MEDICAL_LABEL_KEYWORDS):
        return True
    return any(keyword in body_text for keyword in _MEDICAL_BODY_KEYWORDS)


def _is_medical_item(item: LLMItem) -> bool:
    return item.category in _MEDICAL_CATEGORIES


def _is_reliable_medical_item(item: LLMItem) -> bool:
    if not _is_medical_item(item):
        return False
    if item.confidence < _MEDICAL_CONFIDENCE_THRESHOLD:
        return False
    return bool(collapse_ws(item.evidence_quote))


def _has_reliable_medical_llm_item(guest_llm_items: list[LLMItem]) -> bool:
    return any(_is_reliable_medical_item(item) for item in guest_llm_items)


def _reliable_medical_remark_labels(guest_llm_items: list[LLMItem]) -> set[str]:
    labels: set[str] = set()
    for item in guest_llm_items:
        if not _is_reliable_medical_item(item):
            continue
        mapped_labels = _MEDICAL_REMARK_LABELS_BY_CATEGORY.get(item.category)
        if mapped_labels:
            labels.update(mapped_labels)
    return labels


def _flatten_rewritable_groups(rewritable_by_category: dict[str, list[str]]) -> list[str]:
    flattened: list[str] = []
    for remarks in rewritable_by_category.values():
        _append_unique_remarks(flattened, remarks)
    return flattened


def _relabel_to_category(category: str, remarks: list[str]) -> list[str]:
    """Relabel each remark's ``[label]`` to match the assigned *category*.

    A remark is relabeled when:
    1. Content-based refinement changed the category (``mapped != category``), or
    2. The original label was not in ``_RULE_LABEL_TO_CATEGORY`` (unmapped).
    """
    result: list[str] = []
    for remark in remarks:
        label, _ = _parse_remark_category(remark)
        if label is None:
            # No [label] bracket found (e.g. plain text or inquiry-prefix only).
            # Skip relabeling to avoid corrupting the remark structure.
            result.append(remark)
            continue
        raw_label = label.lower()
        mapped = _RULE_LABEL_TO_CATEGORY.get(raw_label, "other")
        if mapped != category or raw_label not in _RULE_LABEL_TO_CATEGORY:
            result.append(_relabel_remark(remark, category))
        else:
            result.append(remark)
    return result


def _group_rule_rewritable_remarks(
    candidate_remarks: list[str],
) -> tuple[list[str], dict[str, list[str]], int]:
    keep_raw: list[str] = []
    rewritable_by_category: dict[str, list[str]] = {}
    candidate_count = 0
    for remark in candidate_remarks:
        cleaned = _strip_internal_signature_suffix(collapse_ws(remark))
        if not cleaned:
            continue
        if _is_fnl_shared_remark(cleaned):
            _append_unique_remarks(keep_raw, [cleaned])
            continue
        label, body = _parse_remark_category(cleaned)
        raw_label = (label or "other").lower()
        category = _RULE_LABEL_TO_CATEGORY.get(raw_label, "other")
        category = _refine_category_by_content(category, body or cleaned)
        category_bucket = rewritable_by_category.setdefault(category, [])
        if cleaned not in category_bucket:
            category_bucket.append(cleaned)
            candidate_count += 1
    return keep_raw, rewritable_by_category, candidate_count


def _reliable_medical_handoff_texts(guest_llm_items: list[LLMItem]) -> set[str]:
    texts: set[str] = set()
    for item in guest_llm_items:
        if _is_reliable_medical_item(item) and item.handoff_text:
            texts.add(collapse_ws(item.handoff_text))
    return texts


def _group_llm_remarks_by_category(
    llm_remarks: list[str],
    *,
    skip_vip_label: bool,
    reliable_medical_labels: set[str],
    reliable_medical_texts: set[str],
) -> dict[str, list[str]]:
    def _normalize_llm_remark_and_category(remark: str) -> tuple[str, str]:
        label, body = _parse_remark_category(remark)
        category = (label or "other").lower()
        if category != "other":
            return remark, category
        refined_category = _refine_category_by_content("other", body or remark)
        if refined_category == "other":
            return remark, category
        return _relabel_remark(remark, refined_category), refined_category

    grouped: dict[str, list[str]] = {}
    for remark in _mergeable_llm_remarks(llm_remarks, skip_vip_label=skip_vip_label):
        normalized_remark, category = _normalize_llm_remark_and_category(remark)
        if skip_vip_label and category == "vip":
            continue
        if _is_medical_like_remark(normalized_remark):
            if category not in reliable_medical_labels:
                continue
            _, body = _parse_remark_category(normalized_remark)
            if body and collapse_ws(body) not in reliable_medical_texts:
                continue
        grouped.setdefault(category, [])
        if normalized_remark not in grouped[category]:
            grouped[category].append(normalized_remark)
    return grouped


def _rewrite_remarks(
    candidate_remarks: list[str],
    *,
    guest_llm_remarks: list[str],
    guest_llm_items: list[LLMItem],
    llm_extraction_success: bool,
    skip_vip_label: bool,
) -> tuple[list[str], RewriteStats]:
    keep_raw, rewritable_by_category, candidate_count = _group_rule_rewritable_remarks(
        candidate_remarks,
    )
    if not rewritable_by_category:
        return keep_raw, RewriteStats(candidates=0, applied=0, fallback=0)

    stats = RewriteStats(candidates=candidate_count, applied=0, fallback=0)
    rewritable_out: list[str] = []
    if not llm_extraction_success:
        for cat, cat_remarks in rewritable_by_category.items():
            _append_unique_remarks(rewritable_out, _relabel_to_category(cat, cat_remarks))
        return [*keep_raw, *rewritable_out], RewriteStats(
            candidates=stats.candidates,
            applied=stats.applied,
            fallback=candidate_count,
        )

    reliable_medical_labels = _reliable_medical_remark_labels(guest_llm_items)
    reliable_medical_texts = _reliable_medical_handoff_texts(guest_llm_items)
    llm_by_category = _group_llm_remarks_by_category(
        guest_llm_remarks,
        skip_vip_label=skip_vip_label,
        reliable_medical_labels=reliable_medical_labels,
        reliable_medical_texts=reliable_medical_texts,
    )
    applied = 0
    fallback = 0
    for category, rule_remarks in rewritable_by_category.items():
        llm_replacement = llm_by_category.get(category)
        is_medical = category in _MEDICAL_CATEGORY_STRINGS
        has_reliable_medical = is_medical and category in reliable_medical_labels
        if llm_replacement and not is_medical:
            _append_unique_remarks(rewritable_out, llm_replacement)
            applied += len(rule_remarks)
        elif llm_replacement and has_reliable_medical:
            needs_supplement = category in _MEDICAL_SUPPLEMENT_STRINGS
            _append_unique_remarks(rewritable_out, llm_replacement)
            if needs_supplement:
                for remark in _relabel_to_category(category, rule_remarks):
                    stripped = _strip_internal_memo_phrases(remark)
                    if stripped and stripped not in rewritable_out:
                        rewritable_out.append(stripped)
            applied += len(rule_remarks)
        else:
            _append_unique_remarks(rewritable_out, _relabel_to_category(category, rule_remarks))
            fallback += len(rule_remarks)
    for category, llm_only_remarks in llm_by_category.items():
        if category in rewritable_by_category:
            continue
        _append_unique_remarks(rewritable_out, llm_only_remarks)
    return [*keep_raw, *rewritable_out], RewriteStats(
        candidates=stats.candidates,
        applied=applied,
        fallback=fallback,
    )
