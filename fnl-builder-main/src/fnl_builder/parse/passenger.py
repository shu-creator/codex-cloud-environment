from __future__ import annotations

import re
from dataclasses import dataclass, field

from fnl_builder.shared.text import collapse_ws
from fnl_builder.shared.types import PassengerData, PassportRecord

_INQUIRY_RE = re.compile(r"\b(?P<main>\d{4,})(?:[-‐ー—/](?P<branch>\d{1,3}))?\b")
_PASSPORT_RE = re.compile(r"\b(?=[A-Z0-9]{7,10}\b)(?=[A-Z0-9]*[A-Z])(?=[A-Z0-9]*\d)[A-Z0-9]+\b")
_DATE_RE = re.compile(r"\b(?P<y>19\d{2}|20\d{2})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})\b")
_DATE_DMY_RE = re.compile(r"\b(?P<d>\d{1,2}),(?P<mon>[A-Z]{3}),(?P<y>19\d{2}|20\d{2})\b")
_PASSENGER_TITLE_RE = re.compile(r"^(MR\.?|MS\.?|MRS\.?|MISS\.?)\s+(.+)", re.IGNORECASE)
_COUNTRY_SUFFIX_RE = re.compile(r"\s+(JAPAN|JAPANESE|USA|UK|CHINA|KOREA)$", re.IGNORECASE)
_ALLCAPS_NAME_RE = re.compile(r"[A-Z][A-Z\s'-]+")
_PPT_MISSING_RE = re.compile(r"PPT未|旅券未|未取得|未")
_HAS_DIGIT_RE = re.compile(r"\d")
_LAND_ONLY_PATTERN = re.compile(r"(ランドオンリー|ﾗﾝﾄﾞｵﾝﾘｰ|LAND\s*ONLY|L\s*[／/]\s*O|Ｌ／Ｏ)", re.IGNORECASE)
_AGE_HINT_RE = re.compile(r"\(\d{1,3}\)")

_MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


@dataclass
class _PassengerParseState:
    guests_by_inquiry: dict[str, list[PassportRecord]] = field(default_factory=dict)
    flags_by_inquiry: dict[str, list[str]] = field(default_factory=dict)


def _dedupe_stable(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _format_date_match(match: re.Match[str]) -> str:
    year = int(match.group("y"))
    month = int(match.group("m"))
    day = int(match.group("d"))
    return f"{year:04d}-{month:02d}-{day:02d}"


def _format_date_dmy_match(match: re.Match[str]) -> str:
    day = int(match.group("d"))
    month = _MONTH_MAP.get(match.group("mon").upper(), 1)
    year = int(match.group("y"))
    return f"{year:04d}-{month:02d}-{day:02d}"


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


def _extract_issue_and_expiry(joined: str) -> tuple[str | None, str | None]:
    dates = [_format_date_dmy_match(match) for match in _DATE_DMY_RE.finditer(joined)]
    if not dates:
        dates = [_format_date_match(match) for match in _DATE_RE.finditer(joined)]
    issue_date = dates[1] if len(dates) >= 2 else None
    expiry_date = dates[2] if len(dates) >= 3 else None
    return issue_date, expiry_date


def _extract_name_from_title(buffer: list[str]) -> tuple[str | None, str | None, str | None]:
    for line in buffer:
        name_match = _PASSENGER_TITLE_RE.match(line)
        if not name_match:
            continue
        title = name_match.group(1).upper().rstrip(".")
        name_part = collapse_ws(name_match.group(2))
        name_part = _COUNTRY_SUFFIX_RE.sub("", name_part)
        family_name, given_name = _split_english_name(name_part)
        return f"{title}. {name_part}", family_name, given_name
    return None, None, None


def _extract_name_fallback(buffer: list[str]) -> tuple[str | None, str | None, str | None]:
    for line in buffer:
        if _HAS_DIGIT_RE.search(line) or "," in line:
            continue
        if not _ALLCAPS_NAME_RE.fullmatch(line):
            continue
        if len(line.split()) < 2:
            continue
        name_part = collapse_ws(line)
        name_part = _COUNTRY_SUFFIX_RE.sub("", name_part)
        family_name, given_name = _split_english_name(name_part)
        return name_part, family_name, given_name
    return None, None, None


def _extract_name_parts(buffer: list[str]) -> tuple[str | None, str | None, str | None]:
    full_name, family_name, given_name = _extract_name_from_title(buffer)
    if full_name:
        return full_name, family_name, given_name
    return _extract_name_fallback(buffer)


def _normalize_inquiry(main: str, branch: str | None) -> str:
    return f"{main}-{branch}" if branch else main


def _is_date_like_eight_digits(value: str) -> bool:
    if len(value) != 8 or not value.isdigit():
        return False
    if not value.startswith(("19", "20")):
        return False
    month = int(value[4:6])
    day = int(value[6:8])
    return 1 <= month <= 12 and 1 <= day <= 31


def _looks_like_new_inquiry_line(line: str, inquiry_match: re.Match[str] | None) -> bool:
    if not inquiry_match:
        return False
    inquiry_main = inquiry_match.group("main")
    if not 8 <= len(inquiry_main) <= 10:
        return False
    if _is_date_like_eight_digits(inquiry_main):
        return False
    line_upper = line.upper()
    near_line_start = inquiry_match.start() < 5
    has_country_hint = "JAPAN" in line_upper
    has_age_hint = bool(_AGE_HINT_RE.search(line))
    return near_line_start or has_country_hint or (has_age_hint and len(inquiry_main) == 10)


def _append_current_block(state: _PassengerParseState, current: str | None, buffer: list[str]) -> None:
    if not current or not buffer:
        return
    joined = " ".join(buffer)
    passport_match = _PASSPORT_RE.search(joined)
    passport_no = passport_match.group(0) if passport_match else None
    issue_date, expiry_date = _extract_issue_and_expiry(joined)
    full_name, family_name, given_name = _extract_name_parts(buffer)

    record = PassportRecord(
        passport_no=passport_no,
        issue_date=issue_date,
        expiry_date=expiry_date,
        full_name=full_name,
        family_name=family_name,
        given_name=given_name,
    )
    state.guests_by_inquiry.setdefault(current, []).append(record)

    flags: list[str] = []
    if not passport_no or _PPT_MISSING_RE.search(joined):
        flags.append("PPT未")
    if _LAND_ONLY_PATTERN.search(joined):
        flags.append("ランドオンリー")
    if flags:
        state.flags_by_inquiry[current] = _dedupe_stable(flags)


def parse_passenger_list(text: str) -> PassengerData:
    state = _PassengerParseState()
    current: str | None = None
    buffer: list[str] = []

    for raw_line in text.splitlines():
        line = collapse_ws(raw_line)
        if not line:
            continue
        inquiry_match = _INQUIRY_RE.search(line)
        is_new_inquiry = _looks_like_new_inquiry_line(line, inquiry_match)
        if is_new_inquiry:
            assert inquiry_match is not None
            _append_current_block(state, current, buffer)
            current = _normalize_inquiry(inquiry_match.group("main"), inquiry_match.group("branch"))
            buffer = [line]
            continue
        if current:
            buffer.append(line)

    _append_current_block(state, current, buffer)
    return PassengerData(
        guests_by_inquiry=state.guests_by_inquiry,
        flags_by_inquiry=state.flags_by_inquiry,
    )
