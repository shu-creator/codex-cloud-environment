from __future__ import annotations

import re
import unicodedata

from fnl_builder.shared.text import collapse_ws
from fnl_builder.shared.types import GuestRecord, InquiryKey, RoomingData

_ROOM_TYPES = {
    "TWN",
    "TSU",
    "SGL",
    "DBL",
    "TRP",
    "TDB",
    "TPL",
    "QDR",
    "QUAD",
}

_ROOM_TYPES_PATTERN = "|".join(sorted(_ROOM_TYPES))
_ROOM_TYPE_RE = re.compile(rf"\b({_ROOM_TYPES_PATTERN})\b", re.IGNORECASE)
_ROOM_TYPE_COMPACT_RE = re.compile(
    rf"\b\d+\s*(?:{_ROOM_TYPES_PATTERN})(?:\s*[+＋]\s*\d+\s*(?:{_ROOM_TYPES_PATTERN}))*\b",
    re.IGNORECASE,
)
_ROOM_TYPE_COUNT_BEFORE_RE = re.compile(
    rf"\b(?P<n>\d+)[ \t]*(?P<t>{_ROOM_TYPES_PATTERN})\b",
    re.IGNORECASE,
)
_ROOM_TYPE_COUNT_AFTER_RE = re.compile(
    rf"\b(?P<t>{_ROOM_TYPES_PATTERN})[ \t]*[-ー－―][ \t]*(?P<n>\d+)\b",
    re.IGNORECASE,
)

_GUEST_TITLE_RE = re.compile(r"\b(MR|MS|MRS|MISS)\.?\b", re.IGNORECASE)
_ASCII_LETTER_RE = re.compile(r"[A-Z]")
_JP_CHAR_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")
_INQUIRY_TOKEN_RE = re.compile(r"\d{7,10}(?:[-‐ー—/]\d{1,3})?")
_ROOM_NUMBER_RE = re.compile(r"[A-Z0-9]{1,6}", re.IGNORECASE)

_COURSE_CODE_PATTERN = r"[A-Z]{1,2}\d{3}[A-Z]{0,2}"
_INQUIRY_RE = re.compile(r"\b(?P<main>\d{4,})(?:[-‐ー—/](?P<branch>\d{1,3}))?\b")
_PASSPORT_RE = re.compile(r"\b(?=[A-Z0-9]{7,10}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+\b")

_COURSE_DATE_RE = re.compile(
    rf"^\s*({_COURSE_CODE_PATTERN})\s+(\d{{2}})-(\d{{2}})-(\d{{2}})\s*[～~]\s*\d{{2}}-\d{{2}}-\d{{2}}",
    re.MULTILINE,
)
_TOUR_NAME_RE = re.compile(
    rf"({_COURSE_CODE_PATTERN})\s+([A-Z]{{2,4}})\s+([A-Z]{{2,4}})\s+(.+?DAYS)",
    re.IGNORECASE,
)
_PAX_RE = re.compile(r"ADT\s*[-–]\s*(\d+)", re.IGNORECASE)
_NOTE_LINE_RE = re.compile(r"^(注\s*\d+|※|Note\b|備考\b|Remarks?\b)", re.IGNORECASE)
_NOTE_PREFIX_RE = re.compile(r"^(注\s*\d+[:：)\]]?\s*|※\s*|Note[:：]?\s*)", re.IGNORECASE)
_SPLIT_MARKER_VALUES = {"同行", "GRP", "同行GRP", "同行GRP有"}


def _dedupe_stable(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _parse_inquiry_keys(text: str) -> list[InquiryKey]:
    keys: list[InquiryKey] = []
    for match in _INQUIRY_RE.finditer(text):
        main = match.group("main")
        branch = match.group("branch")
        keys.append(InquiryKey(main=main, branch=branch))
    return keys


def _split_english_name(full_name: str) -> tuple[str, str]:
    name = collapse_ws(full_name)
    if not name:
        return "", ""
    if "," in name:
        left, right = [part.strip() for part in name.split(",", 1)]
        return left, right
    parts = name.split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _first_compact_room_text(text: str) -> str | None:
    for raw_line in text.splitlines():
        line = collapse_ws(raw_line)
        if not line:
            continue
        if _ROOM_TYPE_COUNT_AFTER_RE.search(line):
            continue
        compact = _ROOM_TYPE_COMPACT_RE.search(line)
        if compact:
            return collapse_ws(compact.group(0))
    return None


def _accumulate_room_counts_from_line(line: str, by_type: dict[str, int]) -> None:
    after_matches = list(_ROOM_TYPE_COUNT_AFTER_RE.finditer(line))
    if after_matches:
        for match in after_matches:
            room_type = match.group("t").upper()
            by_type[room_type] = by_type.get(room_type, 0) + int(match.group("n"))
        return

    for match in _ROOM_TYPE_COUNT_BEFORE_RE.finditer(line):
        room_type = match.group("t").upper()
        by_type[room_type] = by_type.get(room_type, 0) + int(match.group("n"))


def _accumulate_room_counts_from_text(text: str) -> dict[str, int]:
    by_type: dict[str, int] = {}
    for raw_line in text.splitlines():
        line = collapse_ws(raw_line)
        if not line:
            continue
        _accumulate_room_counts_from_line(line, by_type)
    return by_type


def _filter_positive_room_counts(by_type: dict[str, int]) -> dict[str, int]:
    return {room_type: count for room_type, count in by_type.items() if count > 0}


def _detect_room_counts(text: str) -> tuple[str | None, dict[str, int]]:
    declared_text = _first_compact_room_text(text)
    by_type = _accumulate_room_counts_from_text(text)
    if not by_type and declared_text:
        for match in _ROOM_TYPE_COUNT_AFTER_RE.finditer(declared_text):
            room_type = match.group("t").upper()
            by_type[room_type] = by_type.get(room_type, 0) + int(match.group("n"))
        for match in _ROOM_TYPE_COUNT_BEFORE_RE.finditer(declared_text):
            room_type = match.group("t").upper()
            by_type[room_type] = by_type.get(room_type, 0) + int(match.group("n"))

    by_type = _filter_positive_room_counts(by_type)
    if by_type and not declared_text:
        declared_text = "+".join(f"{count}{room_type}" for room_type, count in by_type.items())
    return declared_text, by_type


def _has_room_type(line: str) -> bool:
    return bool(_ROOM_TYPE_RE.search(line))


def _looks_like_guest_line(line: str) -> bool:
    if _GUEST_TITLE_RE.search(line):
        return True
    tokens = [token for token in line.split() if _ASCII_LETTER_RE.search(token)]
    if not tokens:
        return False
    noise = {"ROOMING", "LIST", "NAME", "NO", "TOTAL", "ADT", "CHD", "INF", "TC", "T/C"}
    tokens = [token for token in tokens if token.upper() not in _ROOM_TYPES and token.upper() not in noise]
    return len(tokens) >= 2


def _is_split_marker_line(line: str) -> bool:
    normalized = unicodedata.normalize("NFKC", line or "")
    compact = re.sub(r"\s+", "", normalized).upper()
    return compact in _SPLIT_MARKER_VALUES


def _merge_split_rooming_rows(text: str) -> list[str]:
    merged_lines: list[str] = []
    pending: str | None = None
    for raw_line in text.splitlines():
        line = collapse_ws(raw_line)
        if not line:
            continue
        if pending:
            if _is_split_marker_line(line):
                continue
            if _INQUIRY_RE.search(line) and not _has_room_type(line):
                merged_lines.append(f"{pending} {line}")
                pending = None
                continue
            merged_lines.append(pending)
            pending = None
        if _has_room_type(line) and not _INQUIRY_RE.search(line) and _looks_like_guest_line(line):
            pending = line
            continue
        merged_lines.append(line)
    if pending:
        merged_lines.append(pending)
    return merged_lines


def _extract_header_fields(text: str) -> tuple[str | None, str | None, str | None, int | None, str | None, dict[str, int]]:
    tour_ref: str | None = None
    tour_name: str | None = None
    depart_date: str | None = None
    declared_total_pax: int | None = None

    course_date_match = _COURSE_DATE_RE.search(text)
    if course_date_match:
        course_code = course_date_match.group(1)
        yy = course_date_match.group(2)
        mm = course_date_match.group(3)
        dd = course_date_match.group(4)
        tour_ref = f"{course_code} {mm}{dd}"
        year = 2000 + int(yy)
        depart_date = f"{year:04d}-{mm}-{dd}"

    tour_name_match = _TOUR_NAME_RE.search(text)
    if tour_name_match:
        tour_name = collapse_ws(tour_name_match.group(0))

    total_pax = sum(int(match.group(1)) for match in _PAX_RE.finditer(text))
    if total_pax > 0:
        declared_total_pax = total_pax

    declared_rooms_text, declared_rooms_by_type = _detect_room_counts(text)
    return tour_ref, tour_name, depart_date, declared_total_pax, declared_rooms_text, declared_rooms_by_type


def _extract_rooming_notes_by_inquiry(text: str) -> dict[str, list[str]]:
    notes_by_inquiry: dict[str, list[str]] = {}
    for line in text.splitlines():
        line_stripped = line.strip()
        if not line_stripped or not _NOTE_LINE_RE.match(line_stripped):
            continue
        keys = _parse_inquiry_keys(line_stripped)
        if not keys:
            continue
        note_text = _NOTE_PREFIX_RE.sub("", line_stripped)
        note_text = _INQUIRY_RE.sub("", note_text)
        note_text = collapse_ws(note_text)
        if not note_text:
            continue
        for key in keys:
            notes_by_inquiry.setdefault(key.normalized(), []).append(note_text)
    return {key: _dedupe_stable(values) for key, values in notes_by_inquiry.items()}


def _extract_rooming_group_ids_by_inquiry(text: str) -> dict[str, str]:
    group_counter = 0
    group_ids_by_inquiry: dict[str, str] = {}
    for line in text.splitlines():
        if "同行" not in line and "GRP" not in line.upper():
            continue
        keys = _parse_inquiry_keys(line)
        if len(keys) < 2:
            continue
        group_counter += 1
        group_id = f"GRP{group_counter:02d}"
        for key in keys:
            group_ids_by_inquiry[key.normalized()] = group_id
    return group_ids_by_inquiry


def _rooming_course_code_if_header(line: str) -> str | None:
    course_match = _COURSE_DATE_RE.match(line)
    if course_match:
        return course_match.group(1)
    return None


def _rooming_inquiry_and_room_type(line: str) -> tuple[InquiryKey, str] | None:
    inquiry_match = _INQUIRY_RE.search(line)
    if not inquiry_match:
        return None
    room_type_match = _ROOM_TYPE_RE.search(line)
    if not room_type_match:
        return None
    inquiry = InquiryKey(main=inquiry_match.group("main"), branch=inquiry_match.group("branch"))
    return inquiry, room_type_match.group(1).upper()


def _rooming_parse_name_and_room_number(line: str) -> tuple[str, str, str, str | None]:
    line_body = re.sub(r"^\d+\s+", "", line)
    jp_match = _JP_CHAR_RE.search(line_body)
    ascii_prefix = line_body[: jp_match.start()] if jp_match else line_body
    tokens = ascii_prefix.split()

    tokens = [token for token in tokens if not _INQUIRY_TOKEN_RE.fullmatch(token) and token.upper() not in _ROOM_TYPES]

    room_number: str | None = None
    if not jp_match and tokens and _ROOM_NUMBER_RE.fullmatch(tokens[-1]) and not _PASSPORT_RE.fullmatch(tokens[-1]):
        candidate = tokens[-1]
        # Pure alphabetic tokens of 2+ chars are likely names, not room numbers.
        # Room numbers are short codes: "A", "101", "B2", etc.
        if len(candidate) == 1 or any(c.isdigit() for c in candidate):
            room_number = candidate
            tokens = tokens[:-1]

    title = None
    if tokens and tokens[0].upper().rstrip(".") in {"MR", "MS", "MRS", "MISS"}:
        title = tokens[0].upper().rstrip(".")
        tokens = tokens[1:]

    name_tokens = [token for token in tokens if _ASCII_LETTER_RE.search(token)]
    name_guess = collapse_ws(" ".join(name_tokens)) if name_tokens else ""
    if not name_guess or len(name_tokens) < 2 or max(len(token) for token in name_tokens) < 2:
        name_guess = ""

    full_name = f"{title}. {name_guess}" if title and name_guess else name_guess
    family_name, given_name = _split_english_name(name_guess)
    return full_name, family_name, given_name, room_number


def _rooming_get_or_assign_room_group_id(
    room_group_key: tuple[str, str, str],
    room_group_by_key: dict[tuple[str, str, str], str],
    room_group_counter: int,
) -> tuple[str, int]:
    if room_group_key not in room_group_by_key:
        room_group_counter += 1
        room_group_by_key[room_group_key] = f"ROOM{room_group_counter:03d}"
    return room_group_by_key[room_group_key], room_group_counter


def _extract_rooming_guests(merged_lines: list[str], group_ids_by_inquiry: dict[str, str]) -> list[GuestRecord]:
    current_course_code: str | None = None
    course_by_inquiry: dict[str, str] = {}
    guests: list[GuestRecord] = []
    room_group_by_key: dict[tuple[str, str, str], str] = {}
    room_group_counter = 0

    for line in merged_lines:
        if not line:
            continue

        course_code = _rooming_course_code_if_header(line)
        if course_code:
            current_course_code = course_code
            continue

        parsed = _rooming_inquiry_and_room_type(line)
        if not parsed:
            continue
        inquiry, room_type = parsed

        if current_course_code and inquiry.main not in course_by_inquiry:
            course_by_inquiry[inquiry.main] = current_course_code

        full_name, family_name, given_name, room_number = _rooming_parse_name_and_room_number(line)
        room_group_key = (inquiry.main, room_type, room_number or "")
        room_group_id, room_group_counter = _rooming_get_or_assign_room_group_id(
            room_group_key,
            room_group_by_key,
            room_group_counter,
        )

        guest = GuestRecord(
            inquiry=inquiry,
            full_name=full_name or inquiry.normalized(),
            family_name=family_name,
            given_name=given_name,
            room_type=room_type,
            room_number=room_number,
            room_group_id=room_group_id,
            group_id=group_ids_by_inquiry.get(inquiry.normalized()),
            course_code=course_by_inquiry.get(inquiry.main),
        )
        guests.append(guest)
    return guests


def parse_rooming_list(text: str) -> RoomingData:
    merged_lines = _merge_split_rooming_rows(text)
    (
        tour_ref,
        tour_name,
        depart_date,
        declared_total_pax,
        declared_rooms_text,
        declared_rooms_by_type,
    ) = _extract_header_fields(text)
    notes_by_inquiry = _extract_rooming_notes_by_inquiry(text)
    group_ids_by_inquiry = _extract_rooming_group_ids_by_inquiry(text)
    guests = _extract_rooming_guests(merged_lines, group_ids_by_inquiry)
    return RoomingData(
        tour_ref=tour_ref,
        tour_name=tour_name,
        depart_date=depart_date,
        declared_total_pax=declared_total_pax,
        declared_rooms_text=declared_rooms_text,
        declared_rooms_by_type=declared_rooms_by_type,
        guests=guests,
        notes_by_inquiry=notes_by_inquiry,
        group_ids_by_inquiry=group_ids_by_inquiry,
    )
