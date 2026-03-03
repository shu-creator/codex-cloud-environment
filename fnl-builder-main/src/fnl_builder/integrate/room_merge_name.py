"""Name-based room merge: alias extraction, fuzzy match, candidate detection."""
from __future__ import annotations

import re
import unicodedata

from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import NameRoomCandidate, RoomMergeInfo

_ROOM_TYPES_NONCAP = r"(?:TWN|DBL|SGL|TSU|TPL|TRP)"
_NAME_SAME_ROOM_RE = re.compile(
    rf"(?P<name_a>[A-Za-zぁ-んァ-ヶ一-龯ｦ-ﾟー・･\s]{{1,40}}?)\s*と\s*"
    rf"(?P<name_b>[A-Za-zぁ-んァ-ヶ一-龯ｦ-ﾟー・･\s]{{1,40}}?)\s*(?:は|が)?\s*同室"
    rf"(?:[（(]\s*\d*\s*(?P<room_type>{_ROOM_TYPES_NONCAP})\s*[)）])?",
    re.IGNORECASE,
)
_HASH_INQ_WITH_TAIL_RE = re.compile(
    r"[#＃](\d{7,10})(?P<tail>(?:(?![#＃]\d{7,10})[^\n])*)",
)
_ALIAS_TRIM_PREFIX_RE = re.compile(r"^[\s:：\-‐ー—,、.。・･*＊★☆]+")
_ALIAS_TRIM_SUFFIX_RE = re.compile(r"(?:様|さん|氏)\s*$")
_ALIAS_SPLIT_RE = re.compile(
    r"(?:と同|同室|同GRP|同グループ|同行|部屋割り|[（(])", re.IGNORECASE,
)
_CURRENT_INQUIRY_PDF_RE = re.compile(r"(\d{10})-(\d{3})")
_CURRENT_INQUIRY_CSV_RE = re.compile(r"\[問合せNO:\s*(\d{7,10})\]")

_SMALL_KANA = "ゃゅょぁぃぅぇぉャュョァィゥェォ"
_ALIAS_FUZZY_MIN_LEN = 5
_GLOBAL_ALIAS_NO_CONTEXT = "__NO_CONTEXT__"


def _normalize_inquiry(inquiry: str) -> str:
    return normalize_inquiry_main(inquiry)


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_alias_name(name: str) -> str:
    """Normalize a candidate name for alias matching."""
    normalized = unicodedata.normalize("NFKC", name or "")
    normalized = _ALIAS_TRIM_PREFIX_RE.sub("", normalized)
    normalized = _ALIAS_TRIM_SUFFIX_RE.sub("", normalized)
    normalized = re.sub(r"[・･/／()（）\[\]【】「」『』\s]", "", normalized)
    return normalized.upper()


def _loose_alias_key(key: str) -> str:
    if not key:
        return ""
    loose = key.replace("ー", "")
    loose = re.sub(rf"([{_SMALL_KANA}])[ウう]", r"\1", loose)
    return loose


def _lookup_alias_inquiries(
    alias_key: str, aliases_by_name: dict[str, set[str]],
) -> set[str]:
    if not alias_key or not aliases_by_name:
        return set()
    inquiries = aliases_by_name.get(alias_key)
    if inquiries:
        return set(inquiries)
    if len(alias_key) < _ALIAS_FUZZY_MIN_LEN:
        return set()
    loose_key = _loose_alias_key(alias_key)
    if not loose_key or len(loose_key) < _ALIAS_FUZZY_MIN_LEN:
        return set()
    resolved: set[str] = set()
    for candidate_key, candidate_inquiries in aliases_by_name.items():
        if len(candidate_key) < _ALIAS_FUZZY_MIN_LEN:
            continue
        if _loose_alias_key(candidate_key) == loose_key:
            resolved.update(candidate_inquiries)
    return resolved


def _extract_unambiguous_global_inquiries(
    contexts: dict[str, set[str]],
) -> set[str]:
    non_empty = [inqs for inqs in contexts.values() if inqs]
    if len(non_empty) != 1:
        return set()
    return set(non_empty[0])


def _lookup_global_alias_inquiries(
    alias_key: str,
    aliases_by_name_global: dict[str, dict[str, set[str]]],
) -> set[str]:
    if not alias_key or not aliases_by_name_global:
        return set()
    direct_contexts = aliases_by_name_global.get(alias_key)
    if direct_contexts:
        direct = _extract_unambiguous_global_inquiries(direct_contexts)
        if direct:
            return direct
    if len(alias_key) < _ALIAS_FUZZY_MIN_LEN:
        return set()
    loose_key = _loose_alias_key(alias_key)
    if not loose_key or len(loose_key) < _ALIAS_FUZZY_MIN_LEN:
        return set()
    resolved: set[str] = set()
    for candidate_key, contexts in aliases_by_name_global.items():
        if len(candidate_key) < _ALIAS_FUZZY_MIN_LEN:
            continue
        if _loose_alias_key(candidate_key) != loose_key:
            continue
        unambiguous = _extract_unambiguous_global_inquiries(contexts)
        if unambiguous:
            resolved.update(unambiguous)
    return resolved


def _clean_candidate_name(raw_name: str) -> str:
    cleaned = _collapse_ws(unicodedata.normalize("NFKC", raw_name or ""))
    cleaned = _ALIAS_TRIM_PREFIX_RE.sub("", cleaned)
    cleaned = _ALIAS_TRIM_SUFFIX_RE.sub("", cleaned)
    return cleaned.strip(" ・･")


def _is_plausible_alias_name(name: str) -> bool:
    if not name or len(name) > 40:
        return False
    return bool(re.search(r"[A-Za-zぁ-んァ-ヶ一-龯ｦ-ﾟ]", name))


def _extract_alias_name_from_tail(tail: str) -> str | None:
    normalized_tail = unicodedata.normalize("NFKC", tail or "")
    normalized_tail = _ALIAS_TRIM_PREFIX_RE.sub("", normalized_tail)
    if not normalized_tail:
        return None
    head = _ALIAS_SPLIT_RE.split(normalized_tail, maxsplit=1)[0]
    tokens = [token for token in re.split(r"\s+", head.strip()) if token]
    if len(tokens) >= 2:
        for token in reversed(tokens):
            token_name = _clean_candidate_name(token)
            if _is_plausible_alias_name(token_name):
                return token_name
    alias_name = _clean_candidate_name(head)
    if _is_plausible_alias_name(alias_name):
        return alias_name
    return None


def _extract_aliases_from_line(line: str) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for match in _HASH_INQ_WITH_TAIL_RE.finditer(line):
        inquiry = _normalize_inquiry(match.group(1))
        alias_name = _extract_alias_name_from_tail(match.group("tail"))
        if not alias_name:
            continue
        alias_key = normalize_alias_name(alias_name)
        if not alias_key:
            continue
        aliases.append((alias_key, inquiry))
    return aliases


def _extract_context_inquiry(line: str) -> str | None:
    pdf_m = _CURRENT_INQUIRY_PDF_RE.search(line)
    if pdf_m:
        return _normalize_inquiry(pdf_m.group(1))
    csv_m = _CURRENT_INQUIRY_CSV_RE.search(line)
    if csv_m:
        return _normalize_inquiry(csv_m.group(1))
    return None


def _copy_aliases(aliases_by_name: dict[str, set[str]]) -> dict[str, set[str]]:
    return {name: set(inquiries) for name, inquiries in aliases_by_name.items()}


def _extract_global_aliases_by_name(
    text: str,
) -> dict[str, dict[str, set[str]]]:
    aliases_by_name: dict[str, dict[str, set[str]]] = {}
    current_inquiry: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        context_inquiry = _extract_context_inquiry(line)
        if context_inquiry:
            current_inquiry = context_inquiry
        context_key = current_inquiry or _GLOBAL_ALIAS_NO_CONTEXT
        for alias_key, inquiry in _extract_aliases_from_line(line):
            aliases_by_name.setdefault(alias_key, {})
            aliases_by_name[alias_key].setdefault(context_key, set()).add(inquiry)
    return aliases_by_name


def extract_name_room_candidates(text: str) -> list[NameRoomCandidate]:
    """Extract name-based same-room candidates from ML text."""
    global_aliases = _extract_global_aliases_by_name(text)
    candidates: list[NameRoomCandidate] = []
    current_inquiry: str | None = None
    aliases_by_name: dict[str, set[str]] = {}
    next_id = 1

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        context_inquiry = _extract_context_inquiry(line)
        if context_inquiry and context_inquiry != current_inquiry:
            current_inquiry = context_inquiry
            aliases_by_name = {}
        elif context_inquiry:
            current_inquiry = context_inquiry

        for alias_name, inquiry in _extract_aliases_from_line(line):
            aliases_by_name.setdefault(alias_name, set()).add(inquiry)

        normalized_line = unicodedata.normalize("NFKC", line)
        for match in _NAME_SAME_ROOM_RE.finditer(normalized_line):
            name_a = _clean_candidate_name(match.group("name_a"))
            name_b = _clean_candidate_name(match.group("name_b"))
            if not _is_plausible_alias_name(name_a):
                continue
            if not _is_plausible_alias_name(name_b):
                continue
            if normalize_alias_name(name_a) == normalize_alias_name(name_b):
                continue
            room_type = (match.group("room_type") or "").upper() or None
            candidates.append(
                NameRoomCandidate(
                    candidate_id=next_id,
                    line_no=line_no,
                    line_text=line,
                    name_a=name_a,
                    name_b=name_b,
                    room_type=room_type,
                    context_inquiry=current_inquiry,
                    aliases_by_name=_copy_aliases(aliases_by_name),
                    aliases_by_name_global=global_aliases,
                ),
            )
            next_id += 1
    return candidates


def resolve_name_candidate_by_rule(
    candidate: NameRoomCandidate,
    known_output_inquiries: set[str],
) -> RoomMergeInfo | None:
    """Try to resolve a name candidate to a RoomMergeInfo using rule-based alias lookup."""
    key_a = normalize_alias_name(candidate.name_a)
    key_b = normalize_alias_name(candidate.name_b)
    inquiries_a = _lookup_alias_inquiries(key_a, candidate.aliases_by_name)
    if not inquiries_a:
        inquiries_a = _lookup_global_alias_inquiries(key_a, candidate.aliases_by_name_global)
    inquiries_b = _lookup_alias_inquiries(key_b, candidate.aliases_by_name)
    if not inquiries_b:
        inquiries_b = _lookup_global_alias_inquiries(key_b, candidate.aliases_by_name_global)
    if len(inquiries_a) != 1 or len(inquiries_b) != 1:
        return None
    inquiry_a = next(iter(inquiries_a))
    inquiry_b = next(iter(inquiries_b))
    if inquiry_a == inquiry_b:
        return None
    if inquiry_a not in known_output_inquiries or inquiry_b not in known_output_inquiries:
        return None
    return RoomMergeInfo(
        inquiries=frozenset({inquiry_a, inquiry_b}),
        room_type=candidate.room_type,
        source="rule_name",
    )
