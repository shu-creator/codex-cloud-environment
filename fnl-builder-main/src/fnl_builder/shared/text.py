from __future__ import annotations

import re


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def normalize_inquiry_main(raw: str) -> str:
    return raw.lstrip("0") or "0"


def safe_float(value: str | float | int) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
