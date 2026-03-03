"""Facade: parse + name resolution + group application for room merges."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_group import merge_room_groups, prioritize_room_merge_infos
from fnl_builder.integrate.room_merge_name_flow import resolve_name_based_room_merges
from fnl_builder.integrate.room_merge_name_llm import resolve_name_candidates_with_llm
from fnl_builder.integrate.room_merge_parse import parse_room_assignments
from fnl_builder.shared.types import GuestRecord, Issue, RoomMergeInfo


def apply_room_merges(
    *,
    ml_text: str,
    guests: list[GuestRecord],
    known_inquiries: set[str],
    llm_provider: str,
    issues: list[Issue],
) -> None:
    """Apply all room merge sources to guest records in-place.

    1. Parse ID-based merges from ML text (``#inq1と#inq2 同室``)
    2. Resolve name-based merges (rule → LLM fallback)
    3. Prioritize and deduplicate
    4. Apply to guest room_group_id
    """
    id_merges = parse_room_assignments(ml_text)

    name_merges: list[RoomMergeInfo] = []
    if ml_text.strip():
        llm_resolver = resolve_name_candidates_with_llm if llm_provider != "none" else None
        name_result, _stats = resolve_name_based_room_merges(
            text=ml_text,
            known_output_inquiries=known_inquiries,
            llm_provider=llm_provider,
            issues=issues,
            llm_resolver=llm_resolver,
        )
        name_merges = name_result

    all_merges = [*id_merges, *name_merges]
    prioritized = prioritize_room_merge_infos(all_merges)
    merge_room_groups(guests, prioritized, issues)
