from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, replace
from pathlib import Path

from fnl_builder.config import PipelineConfig, RunState
from fnl_builder.integrate.guest_builder import (
    process_integrate_guest_data,
    process_post_room_grouping,
)
from fnl_builder.integrate.p_markers import assign_initial_who_id
from fnl_builder.integrate.room_merge import apply_room_merges
from fnl_builder.parse.input_extract import (
    ExtractionMeta,
    PdfExtractionMeta,
    extract_messagelist_text,
    extract_pdf_text,
    text_to_pages,
)
from fnl_builder.parse.messagelist import parse_message_list
from fnl_builder.parse.passenger import parse_passenger_list
from fnl_builder.parse.rooming import parse_rooming_list
from fnl_builder.parse.tour_header_llm import extract_tour_header
from fnl_builder.render.audit import process_audit_warnings, write_audit_log
from fnl_builder.render.excel import render_final_list_workbook
from fnl_builder.llm.adapter import NullAdapter
from fnl_builder.llm.extraction import run_llm_extraction
from fnl_builder.resolve.who_id import who_id_to_inquiry
from fnl_builder.shared.types import (
    GuestRecord,
    IntegrationResult,
    Issue,
    LLMItem,
    MessageListData,
    ParseResult,
    PassengerData,
    PipelineCounts,
    RenderResult,
    RoomingData,
)


_BANNED_PATTERNS = [
    re.compile(r"請求|入金|領収書|残金|クレジット|クレカ|支払|料金"),
    re.compile(r"旅行保険|保険"),
    re.compile(r"社内進行|社内手配|社内"),
]


def _remarks_has_banned(text: str) -> bool:
    return any(p.search(text) for p in _BANNED_PATTERNS)


def parse_stage(state: RunState) -> tuple[ParseResult, list[tuple[int, str]]]:
    """Parse all input files and return (ParseResult, ml_pages)."""
    paths = state.config.input_paths
    rl_text, rl_meta = extract_pdf_text(paths.rooming)
    rooming = parse_rooming_list(rl_text)

    pl_meta: PdfExtractionMeta | None = None
    if paths.passenger:
        pl_text, pl_meta = extract_pdf_text(paths.passenger)
        passenger = parse_passenger_list(pl_text)
    else:
        passenger = PassengerData.empty()

    ml_meta: ExtractionMeta | None = None
    ml_pages: list[tuple[int, str]] = []
    if paths.messagelist:
        is_csv = paths.messagelist.suffix.lower() == ".csv"
        ml_text, ml_meta = extract_messagelist_text(paths.messagelist, is_csv=is_csv)
        messagelist = parse_message_list(ml_text, remarks_has_banned=_remarks_has_banned)
        ml_pages = text_to_pages(ml_text)
    else:
        messagelist = MessageListData.empty()

    tour_header = extract_tour_header(rl_text, state.llm, state.issues)

    meta: dict[str, object] = {"rooming": asdict(rl_meta)}
    if pl_meta is not None:
        meta["passenger"] = asdict(pl_meta)
    if ml_meta is not None:
        meta["messagelist"] = asdict(ml_meta)
    state.audit = replace(state.audit, extraction_meta=meta)

    return ParseResult(
        rooming=rooming,
        passenger=passenger,
        messagelist=messagelist,
        tour_header=tour_header,
    ), ml_pages


def _build_llm_dicts(
    items: list[LLMItem],
    rooming_guests: list[GuestRecord],
) -> tuple[dict[tuple[str, str], list[str]], dict[tuple[str, str], list[LLMItem]]]:
    """Convert flat LLMItem list into per-guest dicts keyed by (inquiry_main, position).

    Uses ``who_id_to_inquiry`` to normalize LLMItem.who_id.
    Items are distributed to ALL guest positions under the same inquiry
    because LLM output does not include per-guest position information.
    Unresolved items are placed under ``("", "0")``.
    """
    from fnl_builder.shared.text import normalize_inquiry_main

    # Build inquiry→positions map from rooming guests
    positions_by_inquiry: dict[str, list[str]] = {}
    position_counter: dict[str, int] = {}
    for guest in rooming_guests:
        inq = normalize_inquiry_main(guest.inquiry.main)
        position_counter[inq] = position_counter.get(inq, 0) + 1
        if guest.inquiry.branch and guest.inquiry.branch.isdigit():
            pos = str(int(guest.inquiry.branch))
        else:
            pos = str(position_counter[inq])
        positions_by_inquiry.setdefault(inq, []).append(pos)

    # Group items by inquiry_main
    items_by_inquiry: dict[str | None, list[LLMItem]] = {}
    for item in items:
        inquiry_main = who_id_to_inquiry(item.who_id) if item.who_id else None
        items_by_inquiry.setdefault(inquiry_main, []).append(item)

    notes: dict[tuple[str, str], list[str]] = {}
    items_dict: dict[tuple[str, str], list[LLMItem]] = {}

    for inquiry_main, inq_items in items_by_inquiry.items():
        if inquiry_main is None:
            # Unresolved items → global fallback key
            key = ("", "0")
            items_dict.setdefault(key, []).extend(inq_items)
            note_list = notes.setdefault(key, [])
            for item in inq_items:
                if item.handoff_text:
                    formatted = f"[{item.category.value}] {item.handoff_text}"
                    if formatted not in note_list:
                        note_list.append(formatted)
            continue

        # Distribute to all positions under this inquiry
        positions = positions_by_inquiry.get(inquiry_main, ["1"])
        for pos in positions:
            key = (inquiry_main, pos)
            items_dict.setdefault(key, []).extend(inq_items)
            note_list = notes.setdefault(key, [])
            for item in inq_items:
                if item.handoff_text:
                    formatted = f"[{item.category.value}] {item.handoff_text}"
                    if formatted not in note_list:
                        note_list.append(formatted)

    return notes, items_dict


def _run_llm_stage(
    state: RunState,
    pages: list[tuple[int, str]],
    course_codes: list[str] | None,
    rooming_guests: list[GuestRecord],
) -> tuple[dict[tuple[str, str], list[str]], dict[tuple[str, str], list[LLMItem]], bool, int]:
    """Run LLM extraction and convert results for integration.

    Returns (llm_notes_by_guest, llm_items_by_guest, success, raw_item_count).
    On failure, records an Issue and returns empty dicts.
    """
    if isinstance(state.llm, NullAdapter):
        return {}, {}, False, 0

    if not pages:
        return {}, {}, False, 0

    try:
        items, success = run_llm_extraction(
            adapter=state.llm,
            pages=pages,
            course_codes=course_codes,
            issues=state.issues,
        )
    except Exception as exc:
        state.issues.append(
            Issue(level="warning", code="llm_fallback", message=f"LLM extraction failed: {exc}")
        )
        return {}, {}, False, 0

    if not success:
        return {}, {}, False, 0

    raw_count = len(items)
    items = assign_initial_who_id(items, pages, state.issues)
    notes, items_dict = _build_llm_dicts(items, rooming_guests)
    return notes, items_dict, True, raw_count


def integrate_stage(
    parsed: ParseResult,
    state: RunState,
    *,
    ml_pages: list[tuple[int, str]] | None = None,
) -> IntegrationResult:
    # Run LLM extraction before integration
    course_codes_list = list(parsed.messagelist.course_by_inquiry.values()) or None
    rooming_guests_list = list(parsed.rooming.guests)
    llm_notes, llm_items, llm_success, llm_raw_count = _run_llm_stage(
        state, ml_pages or [], course_codes_list, rooming_guests_list,
    )
    state.audit = replace(
        state.audit,
        llm_extraction={
            "provider": state.config.llm_provider,
            "success": llm_success,
            "item_count": llm_raw_count,
        },
    )

    guests_out: list[GuestRecord] = []
    stats = process_integrate_guest_data(
        rooming_guests=list(parsed.rooming.guests),
        rooming_notes_by_inquiry=parsed.rooming.notes_by_inquiry,
        passenger_flags_by_inquiry=parsed.passenger.flags_by_inquiry,
        passenger_guests_by_inquiry=parsed.passenger.guests_by_inquiry,
        remarks_by_inquiry=parsed.messagelist.remarks_by_inquiry,
        remarks_by_inquiry_guest=parsed.messagelist.remarks_by_inquiry_guest,
        course_by_inquiry=parsed.messagelist.course_by_inquiry,
        llm_notes_by_guest=llm_notes,
        llm_items_by_guest=llm_items,
        llm_extraction_success=llm_success,
        issues=state.issues,
        guests_out=guests_out,
        remarks_has_banned=_remarks_has_banned,
    )
    if not guests_out:
        state.issues.append(Issue(level="warning", code="no_guests", message="ゲストが0名です"))
    process_post_room_grouping(
        guests=guests_out,
        companion_groups=parsed.messagelist.companion_groups,
    )

    # Apply room merges from ML text (ID-based + name-based)
    ml_text = ""
    if ml_pages:
        ml_text = "\n\n".join(t for _, t in ml_pages)
    if ml_text.strip():
        known = {g.inquiry.main for g in guests_out}
        apply_room_merges(
            ml_text=ml_text,
            guests=guests_out,
            known_inquiries=known,
            llm_provider=state.config.llm_provider,
            issues=state.issues,
        )

    return IntegrationResult(
        guests=guests_out,
        companion_groups=parsed.messagelist.companion_groups,
        stats=stats,
    )


def render_stage(
    integrated: IntegrationResult, state: RunState, *, rooming: RoomingData | None = None
) -> RenderResult:
    paths = state.config.input_paths
    if rooming is None:
        rooming_text, _ = extract_pdf_text(paths.rooming)
        rooming = parse_rooming_list(rooming_text)

    out_pax, _, out_rooms_by_type = process_audit_warnings(
        rooming, integrated.guests, state.issues,
    )
    state.audit = replace(
        state.audit,
        counts=PipelineCounts(
            total_guests=out_pax,
            matched=integrated.stats.applied,
            unmatched=integrated.stats.fallback,
        ),
        issues=list(state.issues),
    )

    render_final_list_workbook(
        template_path=paths.template,
        out_path=paths.output,
        tour_ref=rooming.tour_ref,
        tour_name=rooming.tour_name,
        total_pax=out_pax,
        rooms_by_type=out_rooms_by_type,
        guests=integrated.guests,
        companion_groups=integrated.companion_groups,
        issues=state.issues,
    )

    write_audit_log(state.audit, paths.audit, guest_count=out_pax)

    return RenderResult(output_path=paths.output, audit=state.audit)


def _compute_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest for a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _record_input_hashes(state: RunState) -> None:
    """Record SHA-256 hashes of input files into the audit log."""
    paths = state.config.input_paths
    sha: dict[str, str] = {}
    for label, path in [
        ("rooming", paths.rooming),
        ("passenger", paths.passenger),
        ("messagelist", paths.messagelist),
    ]:
        if path and path.exists():
            sha[label] = _compute_sha256(path)
    state.audit = replace(state.audit, input_files_sha256=sha)


def run(config: PipelineConfig) -> RenderResult:
    state = RunState.from_config(config)
    parsed, ml_pages = parse_stage(state)
    _record_input_hashes(state)

    integrated = integrate_stage(parsed, state, ml_pages=ml_pages)
    return render_stage(integrated, state, rooming=parsed.rooming)
