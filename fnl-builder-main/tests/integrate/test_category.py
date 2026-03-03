from __future__ import annotations

import pytest

from fnl_builder.integrate.category import _parse_remark_category
from fnl_builder.integrate.category import _refine_category_by_content
from fnl_builder.integrate.category import _RULE_LABEL_TO_CATEGORY


def test_rule_label_to_category_keys_are_lowercase() -> None:
    assert all(key == key.lower() for key in _RULE_LABEL_TO_CATEGORY)


def test_rule_label_to_category_full_width_grp_maps_to_group() -> None:
    assert _RULE_LABEL_TO_CATEGORY["別問合せ番号同行ｇｒｐ有"] == "group"


@pytest.mark.parametrize(
    ("category", "remark_body", "expected"),
    [
        ("other", "甲殻類アレルギーがあります", "meal"),
        ("other", "体重 120kg のため延長ベルト希望", "baggage"),
        ("other", "一般的な連絡事項です", "other"),
        ("medical", "ナッツアレルギーあり", "meal"),
        ("medical", "糖尿病でインシュリン使用", "medical"),
        ("medical", "糖尿病だがエビアレルギーあり", "medical"),
        ("other", "同室希望です", "group"),
        ("other", "パスポートの期限が切れそう", "docs"),
        ("other", "ESTA申請済み", "docs"),
        ("other", "Restaurantで食事", "other"),  # ESTA/VISA must not match substrings
        ("other", "合流予定あり", "group"),
    ],
)
def test_refine_category_by_content(category: str, remark_body: str, expected: str) -> None:
    assert _refine_category_by_content(category, remark_body) == expected


@pytest.mark.parametrize(
    ("remark", "expected"),
    [
        ("[medical] ペースメーカー使用", ("medical", "ペースメーカー使用")),
        ("通常の連絡事項", (None, "通常の連絡事項")),
        ("", (None, "")),
    ],
)
def test_parse_remark_category(remark: str, expected: tuple[str | None, str]) -> None:
    assert _parse_remark_category(remark) == expected
