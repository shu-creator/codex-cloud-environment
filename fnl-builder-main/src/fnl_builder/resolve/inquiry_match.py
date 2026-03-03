from __future__ import annotations

from typing import Mapping, TypeVar

from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import InquiryKey

T = TypeVar("T")


def _normalize_branch(branch: str | None) -> str | None:
    if branch is None:
        return None
    if branch.isdigit():
        return str(int(branch))
    return branch


def pick_best_inquiry_match(
    data_by_inquiry: Mapping[str, T],
    inquiry: InquiryKey,
    *,
    guest_count_by_main: dict[str, int],
) -> tuple[str | None, T | None, str | None]:
    """完全一致のみの簡易実装。Phase 5 でファジーマッチング追加。"""
    _ = guest_count_by_main
    main = normalize_inquiry_main(inquiry.main)
    raw_main = inquiry.main
    branch = _normalize_branch(inquiry.branch)
    raw_branch = inquiry.branch
    if branch:
        for m in (main, raw_main):
            for b in dict.fromkeys((branch, raw_branch)):
                candidate = f"{m}-{b}"
                if candidate in data_by_inquiry:
                    return candidate, data_by_inquiry[candidate], None
    if main in data_by_inquiry:
        return main, data_by_inquiry[main], None
    if raw_main in data_by_inquiry:
        return raw_main, data_by_inquiry[raw_main], None
    return None, None, None
