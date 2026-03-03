from __future__ import annotations

import re
from dataclasses import replace

from fnl_builder.resolve.who_id import is_non_participant_name_text
from fnl_builder.resolve.who_id import who_id_to_inquiry_and_branch
from fnl_builder.shared.types import Issue, LLMItem

_PARTICIPANT_LINE_RE = re.compile(r"^(.+?)\s*(\d{10}-\d{3}|CUST-\d{3,4})$")

_P_MARKER_PREFIX = r"(?<![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
_P_MARKER_SUFFIX = r"(?![A-Za-z0-9Ａ-Ｚａ-ｚ０-９])"
_P_MARKER_DIGIT_RE = re.compile(rf"{_P_MARKER_PREFIX}[PＰ]\s*([0-9０-９]{{1,3}}){_P_MARKER_SUFFIX}")
_P_MARKER_CIRCLED_RE = re.compile(rf"{_P_MARKER_PREFIX}[PＰ]\s*([\u2460-\u2473]){_P_MARKER_SUFFIX}")
_P_MARKER_JOINER_RE = re.compile(r"[\s・･/／,、&＆と及び並びに]*")
_FULLWIDTH_DIGITS_TRANS = str.maketrans("０１２３４５６７８９", "0123456789")
_P_MARKER_WINDOW = 64

_P_MARKER_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "medical": ("糖尿", "インシュ", "注射", "血糖", "病状", "病人", "身体障害", "治療", "疾患"),
    "meal": ("アレル", "ｱﾚﾙ", "食事", "ハラール", "ベジ", "甲殻"),
    "mobility": ("車椅", "歩行", "杖", "階段", "段差", "バリア"),
    "hotel": ("禁煙", "喫煙", "低層", "同室", "隣室", "ベッド"),
    "group": ("同室", "同行", "グループ", "部屋割り"),
    "vip_sensitive": ("VIP", "要配慮", "クレーム", "苦情", "トラブル"),
    "schedule": ("離団", "合流", "途中参加", "延泊", "別行程"),
    "documents": ("ビザ", "ESTA", "入国", "税関", "検疫"),
    "communication": ("通訳", "言語", "緊急連絡", "連絡先"),
    "baggage": ("手荷物", "荷物", "機材", "器具", "持込"),
}
_P_MARKER_STRONG_KEYWORDS = ("確/手", "病人", "身体障害", "伺い書", "要配慮")
_P_MARKER_CONTACT_KEYWORDS = ("携帯", "自宅", "入電", "連絡", "折返", "不出", "レラ", "C/B", "コンタクト")


def _iter_p_markers(text: str) -> list[tuple[int, int, int]]:
    markers: list[tuple[int, int, int]] = []

    for match in _P_MARKER_DIGIT_RE.finditer(text):
        normalized = match.group(1).translate(_FULLWIDTH_DIGITS_TRANS)
        try:
            number = int(normalized)
        except ValueError:
            continue
        if 1 <= number <= 999:
            markers.append((number, match.start(), match.end()))

    for match in _P_MARKER_CIRCLED_RE.finditer(text):
        number = ord(match.group(1)) - 0x245F
        if 1 <= number <= 20:
            markers.append((number, match.start(), match.end()))

    markers.sort(key=lambda marker: marker[1])
    return markers


def _score_p_marker_context(category: str, around_text: str, after_text: str) -> int:
    score = 0
    keywords = _P_MARKER_CATEGORY_KEYWORDS.get(category, ())
    if keywords and any(keyword in around_text for keyword in keywords):
        score += 3
    if any(keyword in around_text for keyword in _P_MARKER_STRONG_KEYWORDS):
        score += 3
    if category != "communication" and any(keyword in after_text for keyword in _P_MARKER_CONTACT_KEYWORDS):
        score -= 2
    return score


def _find_quote_line_index(lines: list[str], quote: str) -> int | None:
    if not quote:
        return None

    for index, line in enumerate(lines):
        if quote in line:
            return index

    joined = "\n".join(lines)
    pos = joined.find(quote)
    if pos >= 0:
        return joined[:pos].count("\n")
    return None


def _collect_participants_by_page(
    pages: list[tuple[int, str]],
) -> tuple[
    dict[int, list[str]],
    dict[int, list[tuple[int, str, str]]],
    dict[str, set[str]],
]:
    page_lines: dict[int, list[str]] = {}
    participants_by_page: dict[int, list[tuple[int, str, str]]] = {}
    branches_by_inquiry: dict[str, set[str]] = {}

    for page_no, page_text in pages:
        lines = page_text.splitlines()
        page_lines[page_no] = lines
        rows: list[tuple[int, str, str]] = []
        for index, line in enumerate(lines):
            match = _PARTICIPANT_LINE_RE.match(line.strip())
            if not match:
                continue
            name_part = match.group(1).strip()
            if is_non_participant_name_text(name_part):
                continue
            inquiry_main, branch = who_id_to_inquiry_and_branch(match.group(2))
            if not inquiry_main or not branch:
                continue
            rows.append((index, inquiry_main, branch))
            branches_by_inquiry.setdefault(inquiry_main, set()).add(branch)
        participants_by_page[page_no] = rows

    return page_lines, participants_by_page, branches_by_inquiry


def _build_best_branch_scores(
    *,
    category: str,
    context: str,
    markers: list[tuple[int, int, int]],
    allowed_branches: set[str],
) -> tuple[dict[str, int], dict[str, int]]:
    best_scores: dict[str, int] = {}
    raw_best_scores: dict[str, int] = {}

    for index, (number, position, marker_end) in enumerate(markers):
        branch = str(number)
        cluster_last = index
        while cluster_last + 1 < len(markers):
            next_marker_start = markers[cluster_last + 1][1]
            between = context[markers[cluster_last][2] : next_marker_start]
            if _P_MARKER_JOINER_RE.fullmatch(between):
                cluster_last += 1
                continue
            break

        next_pos = markers[cluster_last + 1][1] if cluster_last + 1 < len(markers) else None
        start = max(0, position - 16)
        base_end = marker_end + _P_MARKER_WINDOW
        if next_pos is not None:
            end = min(len(context), max(position + 1, next_pos))
            end = min(end, base_end)
        else:
            end = min(len(context), base_end)
        around = context[start:end]
        after = context[position : min(len(context), min(end, position + 24))]
        score = _score_p_marker_context(category, around, after)
        raw_best_scores[branch] = max(score, raw_best_scores.get(branch, -999))
        if allowed_branches and branch not in allowed_branches:
            continue
        best_scores[branch] = max(score, best_scores.get(branch, -999))

    return best_scores, raw_best_scores


def _item_context_and_markers(
    item: LLMItem,
    *,
    page_lines: dict[int, list[str]],
    participants_by_page: dict[int, list[tuple[int, str, str]]],
) -> tuple[str, list[tuple[int, int, int]]] | None:
    page_no = item.evidence_page
    quote = item.evidence_quote or ""
    if page_no is None:
        return None
    lines = page_lines.get(page_no)
    if not lines or not quote:
        return None

    quote_idx = _find_quote_line_index(lines, quote)
    if quote_idx is None:
        return None

    participant_rows = participants_by_page.get(page_no, [])
    block_start = 0
    for row_idx, _, _ in participant_rows:
        if row_idx <= quote_idx:
            block_start = row_idx
        else:
            break

    context = "\n".join(lines[block_start : quote_idx + 1])
    markers = _iter_p_markers(context)
    if not markers:
        return None
    return context, markers


def _select_target_branches(
    *,
    item: LLMItem,
    inquiry_main: str,
    current_branch: str | None,
    context: str,
    markers: list[tuple[int, int, int]],
    branches_by_inquiry: dict[str, set[str]],
) -> tuple[list[str], bool]:
    allowed_branches = branches_by_inquiry.get(inquiry_main, set())
    category = item.category.value.lower()
    best_scores, raw_best_scores = _build_best_branch_scores(
        category=category,
        context=context,
        markers=markers,
        allowed_branches=allowed_branches,
    )
    target_branches = sorted((branch for branch, score in best_scores.items() if score >= 3), key=int)
    if target_branches:
        return target_branches, False
    unresolved_candidates = [branch for branch, score in raw_best_scores.items() if branch != (current_branch or "1") and score >= 3]
    return [], bool(unresolved_candidates)


def _expanded_items_for_targets(
    item: LLMItem,
    *,
    inquiry_main: str,
    current_branch: str | None,
    target_branches: list[str],
) -> list[LLMItem]:
    if not target_branches:
        return [item]
    if len(target_branches) == 1 and target_branches[0] == (current_branch or "1"):
        return [item]

    expanded: list[LLMItem] = []
    for target_branch in target_branches:
        expanded.append(
            replace(
                item,
                who_id=f"{inquiry_main}-{int(target_branch):03d}",
            )
        )
    return expanded


def assign_initial_who_id(
    items: list[LLMItem],
    pages: list[tuple[int, str]],
    issues: list[Issue],
) -> list[LLMItem]:
    """Assign who_id to items that lack it, based on participant lines on evidence pages.

    For each item without a who_id, finds the nearest participant header line
    at or above the evidence_quote on the evidence_page.
    """
    if not items or not pages:
        return items

    page_lines_map, participants_by_page, _ = _collect_participants_by_page(pages)

    assigned: list[LLMItem] = []
    unresolved = 0
    for item in items:
        if item.who_id:
            assigned.append(item)
            continue

        page_no = item.evidence_page
        if page_no is None:
            assigned.append(item)
            unresolved += 1
            continue

        lines = page_lines_map.get(page_no, [])
        participants = participants_by_page.get(page_no, [])
        if not lines or not participants:
            assigned.append(item)
            unresolved += 1
            continue

        quote_idx = _find_quote_line_index(lines, item.evidence_quote or "")

        # Find nearest participant at or before the quote
        best: tuple[str, str] | None = None
        for row_idx, inq_main, branch in participants:
            if quote_idx is not None and row_idx <= quote_idx:
                best = (inq_main, branch)
            elif quote_idx is None:
                best = (inq_main, branch)
                break

        if best:
            inq_main, branch = best
            new_who_id = f"{inq_main}-{int(branch):03d}"
            assigned.append(replace(item, who_id=new_who_id))
        else:
            assigned.append(item)
            unresolved += 1

    if unresolved > 0:
        issues.append(
            Issue(
                level="info",
                code="llm_who_id_unresolved",
                message=f"{unresolved}件のLLM抽出結果について対象者を特定できませんでした。",
            )
        )

    return assigned


def reassign_items_by_p_markers(
    items: list[LLMItem],
    pages: list[tuple[int, str]],
    issues: list[Issue],
) -> list[LLMItem]:
    page_lines, participants_by_page, branches_by_inquiry = _collect_participants_by_page(pages)
    reassigned: list[LLMItem] = []
    unresolved_count = 0

    for item in items:
        inquiry_main, current_branch = who_id_to_inquiry_and_branch(item.who_id)
        if not inquiry_main:
            reassigned.append(item)
            continue

        context_and_markers = _item_context_and_markers(
            item,
            page_lines=page_lines,
            participants_by_page=participants_by_page,
        )
        if context_and_markers is None:
            reassigned.append(item)
            continue

        context, markers = context_and_markers
        target_branches, has_unresolved_candidates = _select_target_branches(
            item=item,
            inquiry_main=inquiry_main,
            current_branch=current_branch,
            context=context,
            markers=markers,
            branches_by_inquiry=branches_by_inquiry,
        )
        if has_unresolved_candidates:
            unresolved_count += 1
        reassigned.extend(
            _expanded_items_for_targets(
                item,
                inquiry_main=inquiry_main,
                current_branch=current_branch,
                target_branches=target_branches,
            )
        )

    if unresolved_count > 0:
        issues.append(
            Issue(
                level="warning",
                code="llm_p_marker_unresolved",
                message=f"P番号参照を解決できないLLM抽出結果が{unresolved_count}件あり、元の対象者を維持しました。",
            )
        )

    return reassigned
