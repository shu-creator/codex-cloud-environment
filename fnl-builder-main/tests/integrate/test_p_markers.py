from __future__ import annotations

from fnl_builder.integrate import p_markers
from fnl_builder.shared.types import Category, Issue, LLMItem, Phase


def _make_item(
    *,
    who_id: str = "0067368202-001",
    category: Category = Category.MEDICAL,
    evidence_quote: str = "要配慮 P2",
    evidence_page: int | None = 1,
) -> LLMItem:
    return LLMItem(
        category=category,
        who_id=who_id,
        confidence=0.9,
        phase=Phase.ON_TOUR,
        handoff_text="handoff",
        evidence_quote=evidence_quote,
        summary="",
        evidence_page=evidence_page,
    )


def test_iter_p_markers_digit_and_circled() -> None:
    markers = p_markers._iter_p_markers("P1 と P２ と P① を確認")
    assert [marker[0] for marker in markers] == [1, 2, 1]


def test_score_p_marker_context() -> None:
    score = p_markers._score_p_marker_context("medical", "糖尿の方は P2 です", "P2 です")
    assert score >= 3


def test_find_quote_line_index() -> None:
    lines = ["A", "B", "引用行 C"]
    assert p_markers._find_quote_line_index(lines, "引用行") == 2


def test_collect_participants_by_page() -> None:
    pages = [(1, "山田 太郎 0067368202-001\nメモ: xxxxx\n佐藤 花子 0067368202-002")]
    page_lines, participants_by_page, branches_by_inquiry = p_markers._collect_participants_by_page(pages)

    assert len(page_lines[1]) == 3
    assert participants_by_page[1] == [(0, "67368202", "1"), (2, "67368202", "2")]
    assert branches_by_inquiry["67368202"] == {"1", "2"}


def test_select_target_branches_with_strong_match() -> None:
    item = _make_item()
    context = "病人対応のため P2 を優先"
    markers = p_markers._iter_p_markers(context)

    target_branches, unresolved = p_markers._select_target_branches(
        item=item,
        inquiry_main="67368202",
        current_branch="1",
        context=context,
        markers=markers,
        branches_by_inquiry={"67368202": {"1", "2"}},
    )

    assert target_branches == ["2"]
    assert not unresolved


def test_expanded_items_for_targets() -> None:
    item = _make_item()
    expanded = p_markers._expanded_items_for_targets(
        item,
        inquiry_main="67368202",
        current_branch="1",
        target_branches=["2", "3"],
    )

    assert [candidate.who_id for candidate in expanded] == ["67368202-002", "67368202-003"]
    assert item.who_id == "0067368202-001"


def test_reassign_items_by_p_markers_basic() -> None:
    pages = [(1, "山田 太郎 0067368202-001\n佐藤 花子 0067368202-002\n病人対応のため P2 へ変更")]
    item = _make_item(evidence_quote="病人対応のため P2", evidence_page=1)
    issues: list[Issue] = []

    result = p_markers.reassign_items_by_p_markers([item], pages, issues)

    assert [candidate.who_id for candidate in result] == ["67368202-002"]
    assert issues == []


def test_reassign_items_by_p_markers_unresolved_warning() -> None:
    pages = [(1, "山田 太郎 0067368202-001\n要配慮のため P2 を参照")]
    item = _make_item(evidence_quote="要配慮のため P2", evidence_page=1)
    issues: list[Issue] = []

    result = p_markers.reassign_items_by_p_markers([item], pages, issues)

    assert [candidate.who_id for candidate in result] == ["0067368202-001"]
    assert len(issues) == 1
    assert issues[0].level == "warning"
    assert issues[0].code == "llm_p_marker_unresolved"
