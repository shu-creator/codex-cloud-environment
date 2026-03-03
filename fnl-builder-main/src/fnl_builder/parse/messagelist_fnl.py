from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING, Callable, Protocol

from fnl_builder.parse.messagelist_companion import companion_marker_flags
from fnl_builder.parse.messagelist_rules import (
    _is_pdf_next_record_line,
    _is_pdf_noise_line,
    _repair_pdf_jp_spacing,
)
from fnl_builder.shared.text import collapse_ws

if TYPE_CHECKING:
    pass

_FNL_SHARED_START_RE = re.compile(r"(?:FNL|ﾌｧｲﾅﾙ|ファイナル)\s*時?\s*(?:共有|記載)\s*PLZ", re.IGNORECASE)
_FNL_SHARED_LABEL = "fnl_shared_plz"
_FNL_CHECK_MARKER_RE = re.compile(
    r"(?:FNL\s*時?\s*(?:CHK|チェック|確認|注意)|FNL\s*チェック\s*PLZ|FNL\s*チーム(?:さん)?へ)",
    re.IGNORECASE,
)
_FNL_EXTERNAL_ACTION_RE = re.compile(
    r"(手配|共有|案内|不要|承諾後|現地ガイド|ランドオペレーター|ホテル)",
    re.IGNORECASE,
)
_MEMO_LABEL_PATTERN = r"(?:[【\[〈《(]?\s*後方メモ\s*[】\]〉》)]?\s*[:：]?)"
_FNL_SHARE_LABEL_PATTERN = r"(?:[【\[]?\s*(?:FNL|ﾌｧｲﾅﾙ|ファイナル)\s*時?\s*(?:共有|記載)\s*PLZ\s*[】\]]?\s*[:：]?)"
_FNL_HEADER_ONLY_RE = re.compile(
    rf"^(?:{_MEMO_LABEL_PATTERN}|{_FNL_SHARE_LABEL_PATTERN})$",
    re.IGNORECASE,
)
_FNL_HEADER_PREFIX_RE = re.compile(
    rf"^(?:(?:{_MEMO_LABEL_PATTERN})|(?:{_FNL_SHARE_LABEL_PATTERN}))+",
    re.IGNORECASE,
)
_INTERNAL_SIGNATURE_SUFFIX_RE = re.compile(
    r"\s*(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"
    r"\s+\d{1,2}:\d{2}:\d{2}"
    r"\s+(?P<org>\S*(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション)\S*)"
    r"\s+(?P<name>[A-Za-z一-龯ぁ-んァ-ヶー]{1,20}(?:\s+[A-Za-z一-龯ぁ-んァ-ヶー]{1,20}){0,2})\s*$"
)
_INTERNAL_SIGNATURE_COMPACT_SUFFIX_RE = re.compile(
    r"\s*(?:19|20)\d{2}[/-]\d{1,2}[/-]\d{1,2}"
    r"\s*\d{1,2}:\d{2}:\d{2}"
    r"(?P<org>\S*?(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション))"
    r"(?P<name>[A-Za-z一-龯ぁ-んァ-ヶー〇○●◯]{1,20})\s*$"
)
_INTERNAL_SIGNATURE_MASKED_SUFFIX_RE = re.compile(
    r"\s+(?P<org>\S*(?:部|課|支店|営業所|センター|デスク|オフィス|オペレーション|仕入)\S*)"
    r"\s+(?P<name>[〇○●◯]{1,4})\s*$"
)
_DATE_PREFIX_RE = re.compile(r"^\d{2}-\d{2}\s")
_PDF_ITEM_HEADER_RE = re.compile(r"^\d{2}-\d{2}\s+(?P<category>.+)$")
_INQUIRY_PDF_RE = re.compile(r"(\d{10})-(\d{3})")
_GUEST_ID_RE = re.compile(r"顧客\s+(\d{10})-(\d{3})")
_INQUIRY_CSV_RE = re.compile(r"\[問合せNO:\s*(\d{7,10})\]")


class _FnlResultLike(Protocol):
    fnl_check_required_by_guest: dict[tuple[str, str], int]
    fnl_shared_meta_stripped_count: int


class _FnlStateLike(Protocol):
    current_inquiry: str | None
    current_guest_no: str | None
    is_csv_like: bool
    fnl_shared_active: bool
    fnl_shared_lines: list[str]
    fnl_shared_inquiry: str | None
    fnl_shared_guest_no: str | None
    pending_fnl_check_inquiry: str | None
    pending_fnl_check_guest_no: str | None


def is_fnl_check_line(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text or "")
    return bool(_FNL_CHECK_MARKER_RE.search(normalized))


def has_fnl_external_action(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text or "")
    return bool(_FNL_EXTERNAL_ACTION_RE.search(normalized))


def strip_internal_signature_suffix(text: str) -> tuple[str, bool]:
    source = text or ""
    for pattern in (
        _INTERNAL_SIGNATURE_SUFFIX_RE,
        _INTERNAL_SIGNATURE_COMPACT_SUFFIX_RE,
        _INTERNAL_SIGNATURE_MASKED_SUFFIX_RE,
    ):
        match = pattern.search(source)
        if not match:
            continue
        if "様" in match.group("name"):
            return source.strip(), False
        return source[: match.start()].strip(), True
    return source.strip(), False


def normalize_fnl_shared_line(
    line: str,
    result: _FnlResultLike,
) -> str:
    collapsed = collapse_ws(line)
    if not collapsed:
        return ""
    without_header = _FNL_HEADER_PREFIX_RE.sub("", collapsed).strip()
    candidate = _repair_pdf_jp_spacing(without_header or collapsed)
    compact = re.sub(r"[【】\[\]☆★\s]", "", candidate)
    if _FNL_HEADER_ONLY_RE.match(candidate) or compact in {"後方メモ", "FNL時共有PLZ", "FNL時記載PLZ", "ファイナル時共有PLZ"}:
        return ""
    stripped, removed = strip_internal_signature_suffix(candidate)
    if removed:
        result.fnl_shared_meta_stripped_count += 1
    return collapse_ws(_repair_pdf_jp_spacing(stripped))


def sanitize_fnl_shared_lines(
    lines: list[str],
    result: _FnlResultLike,
) -> list[str]:
    sanitized: list[str] = []
    for line in lines:
        normalized = normalize_fnl_shared_line(line, result)
        if not normalized:
            continue
        if sanitized and normalized == sanitized[-1]:
            continue
        sanitized.append(normalized)
    return sanitized


def record_pending_fnl_check_required(
    result: _FnlResultLike,
    state: _FnlStateLike,
) -> None:
    if not state.pending_fnl_check_inquiry:
        return
    key = (state.pending_fnl_check_inquiry, state.pending_fnl_check_guest_no or "1")
    result.fnl_check_required_by_guest[key] = result.fnl_check_required_by_guest.get(key, 0) + 1
    state.pending_fnl_check_inquiry = None
    state.pending_fnl_check_guest_no = None


def set_pending_fnl_check(state: _FnlStateLike) -> None:
    state.pending_fnl_check_inquiry = state.current_inquiry
    state.pending_fnl_check_guest_no = state.current_guest_no


def resolve_pending_fnl_check_line(
    line: str,
    result: _FnlResultLike,
    state: _FnlStateLike,
) -> None:
    if not state.pending_fnl_check_inquiry:
        return
    if has_fnl_external_action(line):
        state.pending_fnl_check_inquiry = None
        state.pending_fnl_check_guest_no = None
        return
    record_pending_fnl_check_required(result, state)


def consume_non_action_fnl_check_line(
    line: str,
    state: _FnlStateLike,
) -> bool:
    if not is_fnl_check_line(line):
        return False
    if has_fnl_external_action(line):
        return True
    set_pending_fnl_check(state)
    return True


def is_fnl_shared_start_line(line: str) -> bool:
    normalized = unicodedata.normalize("NFKC", line or "")
    return bool(_FNL_SHARED_START_RE.search(normalized))


def is_fnl_shared_end_line(
    line: str,
    state: _FnlStateLike,
) -> bool:
    if not line:
        return False
    has_companion_marker, has_companion_end = companion_marker_flags(line)
    if has_companion_marker or has_companion_end:
        return True
    if _DATE_PREFIX_RE.match(line):
        return True
    if _PDF_ITEM_HEADER_RE.match(line):
        return True
    if _is_pdf_next_record_line(line):
        return True
    if _INQUIRY_PDF_RE.search(line) or _GUEST_ID_RE.search(line):
        return True
    if state.is_csv_like and _INQUIRY_CSV_RE.search(line):
        return True
    return False


def start_fnl_shared_block(state: _FnlStateLike, line: str) -> None:
    state.fnl_shared_active = True
    state.fnl_shared_lines = [line]
    state.fnl_shared_inquiry = state.current_inquiry
    state.fnl_shared_guest_no = state.current_guest_no


def reset_fnl_shared_block(state: _FnlStateLike) -> None:
    state.fnl_shared_active = False
    state.fnl_shared_lines = []
    state.fnl_shared_inquiry = None
    state.fnl_shared_guest_no = None


def flush_fnl_shared_block(
    result: _FnlResultLike,
    state: _FnlStateLike,
    *,
    store_remark: Callable[[str, str | None, str], None],
) -> None:
    if not state.fnl_shared_active or not state.fnl_shared_inquiry:
        reset_fnl_shared_block(state)
        return

    lines = sanitize_fnl_shared_lines(state.fnl_shared_lines, result)
    if not lines:
        reset_fnl_shared_block(state)
        return

    body = collapse_ws(_repair_pdf_jp_spacing(" ".join(lines)))
    remark = f"[問合せNO: {state.fnl_shared_inquiry}] [{_FNL_SHARED_LABEL}] {body}"
    store_remark(
        state.fnl_shared_inquiry,
        state.fnl_shared_guest_no,
        remark,
    )
    reset_fnl_shared_block(state)


def consume_fnl_shared_line(
    line: str,
    result: _FnlResultLike,
    state: _FnlStateLike,
    *,
    store_remark: Callable[[str, str | None, str], None],
) -> bool:
    if not state.fnl_shared_active:
        return False
    if is_fnl_shared_end_line(line, state):
        flush_fnl_shared_block(result, state, store_remark=store_remark)
        return False
    if _is_pdf_noise_line(line):
        return True
    if line:
        state.fnl_shared_lines.append(line)
        return True
    return True
