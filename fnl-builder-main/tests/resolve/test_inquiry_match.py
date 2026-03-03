from __future__ import annotations

from fnl_builder.resolve.inquiry_match import pick_best_inquiry_match
from fnl_builder.shared.types import InquiryKey


def test_pick_exact_match_with_branch() -> None:
    mapping = {"67368202-2": ["note"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202", branch="002"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "67368202-2"
    assert value == ["note"]
    assert ambiguity is None


def test_pick_exact_match_main_only() -> None:
    mapping = {"67368202": ["flag"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "67368202"
    assert value == ["flag"]
    assert ambiguity is None


def test_pick_zero_padded_main_key() -> None:
    mapping = {"0067368202": ["padded"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "0067368202"
    assert value == ["padded"]
    assert ambiguity is None


def test_pick_zero_padded_branch_key() -> None:
    mapping = {"0067368202-2": ["padded_branch"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202", branch="002"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "0067368202-2"
    assert value == ["padded_branch"]
    assert ambiguity is None


def test_pick_raw_branch_zero_padded_key() -> None:
    """upstream parsers may store keys as '0067368202-002' with raw branch."""
    mapping = {"0067368202-002": ["raw_branch"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202", branch="002"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "0067368202-002"
    assert value == ["raw_branch"]
    assert ambiguity is None


def test_pick_normalized_main_raw_branch_key() -> None:
    """normalized main + raw branch: '67368202-002'."""
    mapping = {"67368202-002": ["mixed"]}
    key, value, ambiguity = pick_best_inquiry_match(
        mapping,
        InquiryKey(main="0067368202", branch="002"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key == "67368202-002"
    assert value == ["mixed"]
    assert ambiguity is None


def test_pick_no_match() -> None:
    key, value, ambiguity = pick_best_inquiry_match(
        {"99999999": ["x"]},
        InquiryKey(main="0067368202", branch="1"),
        guest_count_by_main={"0067368202": 1},
    )
    assert key is None
    assert value is None
    assert ambiguity is None
