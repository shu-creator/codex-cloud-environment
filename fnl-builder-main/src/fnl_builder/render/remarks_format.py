from __future__ import annotations

import re
from typing import Iterable

from fnl_builder.shared.text import collapse_ws

_CATEGORY_RE = re.compile(r"^\[(?P<label>[^\]]+)\]\s*(?P<body>.*)$")
_INQUIRY_LABEL_PREFIX_RE = re.compile(r"^\[問合せ\s*NO:\s*\d{7,10}\]\s*", re.IGNORECASE)


def _normalize_remark_category(category: str, body: str) -> str:
    normalized = (category or "").strip().lower()
    if body == "PPT未" and normalized in {"", "other"}:
        return "ppt"
    return normalized or "other"


def _category_for_uncategorized_remark(body: str) -> str:
    if body == "PPT未":
        return "ppt"
    return "other"


def _split_remark_fragments(text: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[;；]+", text or ""):
        normalized = collapse_ws(chunk)
        if normalized:
            parts.append(normalized)
    return parts


def _strip_inquiry_label_prefix(text: str) -> str:
    return _INQUIRY_LABEL_PREFIX_RE.sub("", text or "").strip()


def _dedupe_stable(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def format_guest_remarks(remarks_parts: list[str]) -> str:
    raw_parts = [collapse_ws(part) for part in remarks_parts if collapse_ws(part)]
    raw_parts = [_strip_inquiry_label_prefix(part) for part in raw_parts]
    companion_pattern = r"と同(ｸﾞﾙｰﾌﾟ|グループ)"
    raw_parts = [part for part in raw_parts if not re.match(rf"^{companion_pattern}$", part)]
    raw_parts = [re.sub(rf"[;；\s]*{companion_pattern}$", "", part).strip() for part in raw_parts]
    raw_parts = [part for part in raw_parts if part]
    raw_parts = _dedupe_stable(raw_parts)
    if not raw_parts:
        return ""

    remarks_by_category: dict[str, list[str]] = {}
    category_order: list[str] = []
    for part in raw_parts:
        match = _CATEGORY_RE.match(part)
        if match:
            body = collapse_ws(match.group("body"))
            category = _normalize_remark_category(match.group("label"), body)
        else:
            body = part
            category = _normalize_remark_category(_category_for_uncategorized_remark(body), body)

        if category not in remarks_by_category:
            remarks_by_category[category] = []
            category_order.append(category)
        for fragment in _split_remark_fragments(body):
            remarks_by_category[category].append(fragment)

    out_lines: list[str] = []
    joiner = "\n  "
    for category in category_order:
        bodies = _dedupe_stable(remarks_by_category.get(category, []))
        if not bodies:
            continue
        out_lines.append(f"[{category}] {joiner.join(bodies)}")
    return "\n".join(out_lines)

