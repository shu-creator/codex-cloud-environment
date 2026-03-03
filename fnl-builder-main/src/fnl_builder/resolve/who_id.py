from __future__ import annotations

import re

PARTICIPANT_BANNED_TOKENS = ("備考", "メモ", "連絡先", "顧客メモ", "問い合わせ", "問合せ", "同行者")


def is_non_participant_name_text(name_part: str) -> bool:
    if not name_part:
        return True
    if ":" in name_part or "：" in name_part:
        return True
    if any(token in name_part for token in PARTICIPANT_BANNED_TOKENS):
        return True
    if any(mark in name_part for mark in ("[", "]", "【", "】", "→", "#")):
        return True
    return False


def who_id_to_inquiry_and_branch(who_id: str) -> tuple[str | None, str | None]:
    """Map LLM who_id to (inquiry.main, branch).

    Args:
        who_id: LLM output who_id (e.g., "0067368202-001", "CUST-001")

    Returns:
        (inquiry.main, branch) e.g., ("67368202", "1") or (None, None) if unmappable
        Branch is normalized: "001" -> "1", "002" -> "2"
    """
    if not who_id:
        return None, None

    if who_id.startswith("CUST-"):
        return None, None

    match = re.match(r"^0*(\d+)-(\d{3})$", who_id)
    if match:
        inquiry = match.group(1)
        branch = str(int(match.group(2)))
        return inquiry, branch

    match = re.match(r"^0*(\d+)$", who_id)
    if match:
        return match.group(1), None

    return None, None


def who_id_to_inquiry(who_id: str) -> str | None:
    """Map LLM who_id to GuestRecord.inquiry.main.

    Args:
        who_id: LLM output who_id (e.g., "0067368202-001", "CUST-001")

    Returns:
        inquiry.main (e.g., "67368202") or None if unmappable
    """
    if not who_id:
        return None

    if who_id.startswith("CUST-"):
        return None

    match = re.match(r"^0*(\d+)(?:-\d+)?$", who_id)
    if match:
        return match.group(1)

    return None
