from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from fnl_builder.parse.course_code import extract_course_code
from fnl_builder.parse.messagelist_companion import process_message_list_companions
from fnl_builder.parse.messagelist_fnl import (
    consume_fnl_shared_line,
    consume_non_action_fnl_check_line,
    flush_fnl_shared_block,
    is_fnl_shared_start_line,
    record_pending_fnl_check_required,
    resolve_pending_fnl_check_line,
    start_fnl_shared_block,
)
from fnl_builder.parse.messagelist_rules import (
    _DATE_OPERATOR_PREFIX_RE,
    _DATE_PREFIX_RE,
    _DUMMY_PREFIX_RE,
    _GUEST_ID_RE,
    _INQUIRY_CSV_RE,
    _INQUIRY_PDF_RE,
    _MEMO_INLINE_RE,
    _extract_message_list_remark,
    _has_remark_keyword,
    _is_pdf_item_header,
    _is_pdf_next_record_line,
    _is_pdf_noise_line,
    _normalize_message_list_inquiry,
    _repair_pdf_jp_spacing,
)
from fnl_builder.shared.text import collapse_ws
from fnl_builder.shared.types import MessageListData


@dataclass
class _MutableMessageListResult:
    """Internal mutable accumulator; converted to frozen MessageListData at end."""

    remarks_by_inquiry: dict[str, list[str]] = field(default_factory=dict)
    remarks_by_inquiry_guest: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    course_by_inquiry: dict[str, str] = field(default_factory=dict)
    companion_groups: dict[str, set[str]] = field(default_factory=dict)
    fnl_check_required_by_guest: dict[tuple[str, str], int] = field(default_factory=dict)
    fnl_shared_meta_stripped_count: int = 0

    def freeze(self) -> MessageListData:
        return MessageListData(
            remarks_by_inquiry=self.remarks_by_inquiry,
            remarks_by_inquiry_guest=self.remarks_by_inquiry_guest,
            course_by_inquiry=self.course_by_inquiry,
            companion_groups=self.companion_groups,
            fnl_check_required_by_guest=self.fnl_check_required_by_guest,
            fnl_shared_meta_stripped_count=self.fnl_shared_meta_stripped_count,
        )


@dataclass
class _MessageListParseState:
    current_inquiry: str | None = None
    current_guest_no: str | None = None
    current_course: str | None = None
    is_csv_like: bool = False
    in_companion_section: bool = False
    companion_inquiries: set[str] = field(default_factory=set)
    pdf_block_category: str | None = None
    pdf_block_lines: list[str] = field(default_factory=list)
    pdf_block_inquiry: str | None = None
    pdf_block_guest_no: str | None = None
    fnl_shared_active: bool = False
    fnl_shared_lines: list[str] = field(default_factory=list)
    fnl_shared_inquiry: str | None = None
    fnl_shared_guest_no: str | None = None
    pending_fnl_check_inquiry: str | None = None
    pending_fnl_check_guest_no: str | None = None


def _is_message_list_blank_line(line: str, state: _MessageListParseState) -> bool:
    if line:
        return False
    if state.is_csv_like:
        state.current_inquiry = None
        state.current_guest_no = None
    return True


def _update_message_list_course(line: str, state: _MessageListParseState) -> None:
    course_code = extract_course_code(line)
    if course_code:
        state.current_course = course_code


def _update_message_list_inquiry(line: str, state: _MessageListParseState) -> bool:
    guest_match = _GUEST_ID_RE.search(line)
    if guest_match:
        state.current_inquiry = _normalize_message_list_inquiry(guest_match.group(1))
        state.current_guest_no = str(int(guest_match.group(2)))
        return True

    inquiry_match = _INQUIRY_PDF_RE.search(line)
    if inquiry_match:
        state.current_inquiry = _normalize_message_list_inquiry(inquiry_match.group(1))
        state.current_guest_no = str(int(inquiry_match.group(2)))
        return True

    inquiry_match = _INQUIRY_CSV_RE.search(line)
    if inquiry_match:
        state.current_inquiry = _normalize_message_list_inquiry(inquiry_match.group(1))
        state.current_guest_no = None
        return True
    return False


def _record_course_for_current_inquiry(
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    inquiry_matched: bool,
) -> None:
    if inquiry_matched and state.current_inquiry and state.current_course:
        result.course_by_inquiry[state.current_inquiry] = state.current_course


def _store_remark_for_inquiry_guest(
    result: _MutableMessageListResult,
    inquiry: str,
    guest_no: str | None,
    remark: str,
) -> None:
    if not inquiry:
        return

    remarks = result.remarks_by_inquiry.setdefault(inquiry, [])
    if remark not in remarks:
        remarks.append(remark)

    if guest_no:
        key = (inquiry, guest_no)
        guest_remarks = result.remarks_by_inquiry_guest.setdefault(key, [])
        if remark not in guest_remarks:
            guest_remarks.append(remark)


def _store_remark(result: _MutableMessageListResult, state: _MessageListParseState, remark: str) -> None:
    if not state.current_inquiry:
        return
    _store_remark_for_inquiry_guest(
        result,
        state.current_inquiry,
        state.current_guest_no,
        remark,
    )


def _start_pdf_remark_block(state: _MessageListParseState, category: str) -> None:
    state.pdf_block_category = collapse_ws(category)
    state.pdf_block_lines = []
    state.pdf_block_inquiry = state.current_inquiry
    state.pdf_block_guest_no = state.current_guest_no


def _reset_pdf_remark_block(state: _MessageListParseState) -> None:
    state.pdf_block_category = None
    state.pdf_block_lines = []
    state.pdf_block_inquiry = None
    state.pdf_block_guest_no = None


def _flush_pdf_remark_block(
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> None:
    if not state.pdf_block_category or not state.pdf_block_inquiry:
        _reset_pdf_remark_block(state)
        return

    category = collapse_ws(state.pdf_block_category)
    body = collapse_ws(" ".join(state.pdf_block_lines))
    body = _MEMO_INLINE_RE.sub("", body)
    body = collapse_ws(_repair_pdf_jp_spacing(body))
    body = _DUMMY_PREFIX_RE.sub("", body)
    body = _DATE_OPERATOR_PREFIX_RE.sub("", body)
    body = collapse_ws(_repair_pdf_jp_spacing(body))
    target_text = collapse_ws(f"{category} {body}")

    if not target_text:
        _reset_pdf_remark_block(state)
        return
    if remarks_has_banned(target_text):
        _reset_pdf_remark_block(state)
        return
    if not _has_remark_keyword(target_text):
        _reset_pdf_remark_block(state)
        return

    if body:
        formatted = f"[問合せNO: {state.pdf_block_inquiry}] [{category}] {body}"
    else:
        formatted = f"[問合せNO: {state.pdf_block_inquiry}] [{category}]"
    _store_remark_for_inquiry_guest(
        result,
        state.pdf_block_inquiry,
        state.pdf_block_guest_no,
        formatted,
    )
    _reset_pdf_remark_block(state)


def _update_message_list_line_context(
    line: str,
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> object:
    _update_message_list_course(line, state)
    inquiry_matched = _update_message_list_inquiry(line, state)
    if inquiry_matched and not state.is_csv_like:
        _flush_pdf_remark_block(result, state, remarks_has_banned=remarks_has_banned)
    _record_course_for_current_inquiry(result, state, inquiry_matched)

    if state.is_csv_like:
        return None

    pdf_item_header_match = _is_pdf_item_header(line)
    if pdf_item_header_match:
        _flush_pdf_remark_block(result, state, remarks_has_banned=remarks_has_banned)
        _start_pdf_remark_block(state, pdf_item_header_match.group("category"))
    return pdf_item_header_match


def _process_csv_remark_line(
    line: str,
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> None:
    if state.current_inquiry and _DATE_PREFIX_RE.match(line):
        return
    if not state.current_inquiry:
        return
    remark = _extract_message_list_remark(line, remarks_has_banned=remarks_has_banned)
    if remark:
        _store_remark(result, state, remark)


def _process_pdf_remark_line(
    line: str,
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    pdf_item_header_match: object,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> None:
    if pdf_item_header_match:
        return
    if state.pdf_block_category:
        if _is_pdf_next_record_line(line):
            _flush_pdf_remark_block(result, state, remarks_has_banned=remarks_has_banned)
            return
        if _is_pdf_noise_line(line):
            return
        state.pdf_block_lines.append(line)
        return
    if state.current_inquiry and _DATE_PREFIX_RE.match(line):
        return
    if not state.current_inquiry:
        return
    remark = _extract_message_list_remark(line, remarks_has_banned=remarks_has_banned)
    if remark:
        _store_remark(result, state, remark)


def _start_fnl_shared_if_needed(
    line: str,
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> bool:
    if not is_fnl_shared_start_line(line):
        return False
    _update_message_list_inquiry(line, state)
    if not state.current_inquiry:
        return False
    if not state.is_csv_like:
        _flush_pdf_remark_block(result, state, remarks_has_banned=remarks_has_banned)
    start_fnl_shared_block(state, line)
    return True


def _make_store_remark(result: _MutableMessageListResult) -> Callable[[str, str | None, str], None]:
    def _store(inquiry: str, guest_no: str | None, remark: str) -> None:
        _store_remark_for_inquiry_guest(result, inquiry, guest_no, remark)

    return _store


def _process_message_list_line(
    raw_line: str,
    result: _MutableMessageListResult,
    state: _MessageListParseState,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> None:
    line = raw_line.strip()
    store_remark = _make_store_remark(result)

    if consume_fnl_shared_line(line, result, state, store_remark=store_remark):
        return
    resolve_pending_fnl_check_line(line, result, state)
    if _is_message_list_blank_line(line, state):
        return
    if _start_fnl_shared_if_needed(line, result, state, remarks_has_banned=remarks_has_banned):
        return

    pdf_item_header_match = _update_message_list_line_context(
        line,
        result,
        state,
        remarks_has_banned=remarks_has_banned,
    )

    if process_message_list_companions(line, result, state):
        return
    if consume_non_action_fnl_check_line(line, state):
        return
    if state.is_csv_like:
        _process_csv_remark_line(
            line,
            result,
            state,
            remarks_has_banned=remarks_has_banned,
        )
        return
    _process_pdf_remark_line(
        line,
        result,
        state,
        pdf_item_header_match,
        remarks_has_banned=remarks_has_banned,
    )


def parse_message_list(
    text: str,
    *,
    remarks_has_banned: Callable[[str], bool],
) -> MessageListData:
    result = _MutableMessageListResult()
    state = _MessageListParseState(is_csv_like="[問合せNO:" in text)
    store_remark = _make_store_remark(result)

    for raw_line in text.splitlines():
        _process_message_list_line(
            raw_line,
            result,
            state,
            remarks_has_banned=remarks_has_banned,
        )

    if not state.is_csv_like:
        _flush_pdf_remark_block(result, state, remarks_has_banned=remarks_has_banned)
    if state.fnl_shared_active:
        flush_fnl_shared_block(result, state, store_remark=store_remark)
    record_pending_fnl_check_required(result, state)

    return result.freeze()
