from __future__ import annotations

import pytest

from fnl_builder.resolve.who_id import is_non_participant_name_text
from fnl_builder.resolve.who_id import who_id_to_inquiry
from fnl_builder.resolve.who_id import who_id_to_inquiry_and_branch


@pytest.mark.parametrize(
    ("who_id", "expected"),
    [
        ("0067368202-001", ("67368202", "1")),
        ("0067368202", ("67368202", None)),
        ("CUST-001", (None, None)),
        ("", (None, None)),
    ],
)
def test_who_id_to_inquiry_and_branch(who_id: str, expected: tuple[str | None, str | None]) -> None:
    assert who_id_to_inquiry_and_branch(who_id) == expected


@pytest.mark.parametrize(
    ("who_id", "expected"),
    [
        ("0067368202-001", "67368202"),
        ("0067368202", "67368202"),
        ("CUST-001", None),
        ("", None),
    ],
)
def test_who_id_to_inquiry(who_id: str, expected: str | None) -> None:
    assert who_id_to_inquiry(who_id) == expected


@pytest.mark.parametrize(
    ("name_part", "expected"),
    [
        ("顧客メモ: 要確認", True),
        ("山田太郎→", True),
        ("", True),
        ("山田 太郎", False),
    ],
)
def test_is_non_participant_name_text(name_part: str, expected: bool) -> None:
    assert is_non_participant_name_text(name_part) is expected
