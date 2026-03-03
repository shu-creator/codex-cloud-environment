"""Orchestrate name-based room merge: rule → LLM resolution."""
from __future__ import annotations

import re
from typing import Callable

from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import (
    Issue,
    NameMergeStats,
    NameResolution,
    NameRoomCandidate,
    RoomMergeInfo,
)

from fnl_builder.integrate.room_merge_name import (
    extract_name_room_candidates,
    resolve_name_candidate_by_rule,
)

_ROOM_TYPES_NONCAP = r"(?:TWN|DBL|SGL|TSU|TPL|TRP)"

NameLlmResolver = Callable[
    [list[NameRoomCandidate], str, set[str]], list[NameResolution],
]


def _normalize_room_type(room_type: str | None) -> str | None:
    if not room_type:
        return None
    normalized = room_type.upper().strip()
    if re.fullmatch(_ROOM_TYPES_NONCAP, normalized):
        return normalized
    return None


def _resolve_by_rule(
    candidates: list[NameRoomCandidate],
    known: set[str],
) -> tuple[list[RoomMergeInfo], list[NameRoomCandidate], set[int]]:
    merges: list[RoomMergeInfo] = []
    unresolved: list[NameRoomCandidate] = []
    resolved_ids: set[int] = set()
    for candidate in candidates:
        result = resolve_name_candidate_by_rule(candidate, known)
        if result is None:
            unresolved.append(candidate)
        else:
            merges.append(result)
            resolved_ids.add(candidate.candidate_id)
    return merges, unresolved, resolved_ids


def _build_llm_merge_info(
    item: NameResolution,
    candidate: NameRoomCandidate,
    known: set[str],
) -> RoomMergeInfo | None:
    inquiry_a_raw = item.get("inquiry_a")
    inquiry_b_raw = item.get("inquiry_b")
    if not isinstance(inquiry_a_raw, str) or not isinstance(inquiry_b_raw, str):
        return None
    inquiry_a = normalize_inquiry_main(inquiry_a_raw)
    inquiry_b = normalize_inquiry_main(inquiry_b_raw)
    if inquiry_a == inquiry_b:
        return None
    if inquiry_a not in known or inquiry_b not in known:
        return None
    confidence_raw = item.get("confidence")
    if not isinstance(confidence_raw, (int, float)):
        return None
    confidence = float(confidence_raw)
    if confidence < 0.85 or confidence > 1.0:
        return None
    candidate_rt = _normalize_room_type(candidate.room_type)
    llm_rt_raw = item.get("room_type")
    llm_rt = _normalize_room_type(llm_rt_raw if isinstance(llm_rt_raw, str) else None)
    if candidate_rt and llm_rt and candidate_rt != llm_rt:
        return None
    return RoomMergeInfo(
        inquiries=frozenset({inquiry_a, inquiry_b}),
        room_type=candidate_rt or llm_rt,
        source="llm_name",
        confidence=confidence,
    )


def _resolve_by_llm(
    unresolved: list[NameRoomCandidate],
    known: set[str],
    llm_resolver: NameLlmResolver,
    llm_provider: str,
) -> tuple[list[RoomMergeInfo], set[int]]:
    llm_outputs = llm_resolver(unresolved, llm_provider, known)
    candidates_by_id = {c.candidate_id: c for c in unresolved}
    best: dict[int, RoomMergeInfo] = {}
    for item in llm_outputs:
        cid = item.get("candidate_id")
        if not isinstance(cid, int):
            continue
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        merge_info = _build_llm_merge_info(item, candidate, known)
        if merge_info is None:
            continue
        current = best.get(cid)
        if current is None or (merge_info.confidence or 0.0) > (current.confidence or 0.0):
            best[cid] = merge_info
    return list(best.values()), set(best.keys())


def resolve_name_based_room_merges(
    *,
    text: str,
    known_output_inquiries: set[str],
    llm_provider: str,
    issues: list[Issue],
    llm_resolver: NameLlmResolver | None = None,
) -> tuple[list[RoomMergeInfo], NameMergeStats]:
    """Resolve name-based room merges via rule → LLM fallback."""
    candidates = extract_name_room_candidates(text)
    known = {normalize_inquiry_main(i) for i in known_output_inquiries if i}

    if not candidates:
        return [], NameMergeStats()

    rule_merges, unresolved, rule_ids = _resolve_by_rule(candidates, known)
    rule_resolved = len(rule_ids)

    if not unresolved or llm_provider == "none":
        unresolved_count = len(unresolved)
        if unresolved_count > 0:
            issues.append(Issue(
                level="warning",
                code="room_merge_name_resolution_llm_skipped",
                message=f"名前ベース同室候補{unresolved_count}件はLLM未使用のため未解決でした。",
            ))
        return rule_merges, NameMergeStats(
            candidates=len(candidates),
            rule_resolved=rule_resolved,
            unresolved=unresolved_count,
        )

    llm_merges: list[RoomMergeInfo] = []
    llm_resolved_ids: set[int] = set()
    if llm_resolver is not None:
        llm_merges, llm_resolved_ids = _resolve_by_llm(
            unresolved, known, llm_resolver, llm_provider,
        )

    llm_resolved = len(llm_resolved_ids)
    final_unresolved = len(unresolved) - llm_resolved
    if final_unresolved > 0:
        issues.append(Issue(
            level="warning",
            code="room_merge_name_resolution_unresolved",
            message=f"名前ベース同室候補{final_unresolved}件は解決できませんでした。",
        ))

    return [*rule_merges, *llm_merges], NameMergeStats(
        candidates=len(candidates),
        rule_resolved=rule_resolved,
        llm_resolved=llm_resolved,
        unresolved=max(final_unresolved, 0),
    )
