"""LLM and mock resolvers for name-based room merge candidates."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from fnl_builder.integrate.room_merge_name import (
    normalize_alias_name,
)
from fnl_builder.shared.text import normalize_inquiry_main
from fnl_builder.shared.types import NameResolution, NameRoomCandidate


def _lookup_global(
    alias_key: str,
    aliases_global: dict[str, dict[str, set[str]]],
) -> set[str]:
    """Extract unambiguous inquiries from global alias contexts."""
    contexts = aliases_global.get(alias_key)
    if not contexts:
        return set()
    non_empty = [inqs for inqs in contexts.values() if inqs]
    if len(non_empty) != 1:
        return set()
    return set(non_empty[0])


def _build_prompt(
    candidates: list[NameRoomCandidate],
    known_output_inquiries: set[str],
) -> str:
    payload_candidates: list[dict[str, Any]] = []
    for c in candidates:
        key_a = normalize_alias_name(c.name_a)
        key_b = normalize_alias_name(c.name_b)
        local_a = c.aliases_by_name.get(key_a, set())
        local_b = c.aliases_by_name.get(key_b, set())
        global_a = _lookup_global(key_a, c.aliases_by_name_global)
        global_b = _lookup_global(key_b, c.aliases_by_name_global)
        payload_candidates.append({
            "candidate_id": c.candidate_id,
            "line_text": c.line_text,
            "name_a": c.name_a,
            "name_b": c.name_b,
            "room_type_hint": c.room_type,
            "context_inquiry": c.context_inquiry,
            "name_a_candidates": sorted(local_a or global_a),
            "name_b_candidates": sorted(local_b or global_b),
        })
    return (
        "Resolve same-room candidates to inquiry numbers.\n"
        "Rules:\n"
        "- Use only inquiry numbers from known_output_inquiries.\n"
        "- If either side cannot be determined with confidence, return null.\n"
        "- Do not invent inquiry numbers.\n"
        "- Keep candidate_id unchanged.\n"
        "- confidence must be 0..1.\n\n"
        f"known_output_inquiries={json.dumps(sorted(known_output_inquiries), ensure_ascii=False)}\n"
        f"candidates={json.dumps(payload_candidates, ensure_ascii=False)}"
    )


_RESOLUTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "resolutions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidate_id": {"type": "integer"},
                    "inquiry_a": {"type": ["string", "null"]},
                    "inquiry_b": {"type": ["string", "null"]},
                    "room_type": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "candidate_id", "inquiry_a", "inquiry_b",
                    "room_type", "confidence",
                ],
            },
        },
    },
    "required": ["resolutions"],
}

_OPENAI_ENDPOINT = "https://api.openai.com/v1/responses"
_DEFAULT_MODEL = "gpt-5.2"


def _extract_output_text(parsed: dict[str, Any]) -> str | None:
    output_text = parsed.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = parsed.get("output")
    if not isinstance(output, list):
        return None
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for chunk in content:
                if (
                    isinstance(chunk, dict)
                    and chunk.get("type") == "output_text"
                    and isinstance(chunk.get("text"), str)
                ):
                    parts.append(chunk["text"])
    return "".join(parts) if parts else None


def _resolve_with_openai(
    candidates: list[NameRoomCandidate],
    known: set[str],
) -> list[NameResolution]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return []
    model = os.getenv("OPENAI_MODEL") or _DEFAULT_MODEL
    system_prompt = (
        "You resolve same-room name pairs to inquiry numbers. "
        "Return strict JSON only. Never guess. Use null when uncertain."
    )
    user_prompt = _build_prompt(candidates, known)
    payload: dict[str, object] = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "room_name_resolution",
                "strict": True,
                "schema": _RESOLUTION_SCHEMA,
            },
        },
    }
    req = urllib.request.Request(
        _OPENAI_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            body = response.read().decode("utf-8")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return []
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return []
    text = _extract_output_text(parsed)
    if not text:
        return []
    try:
        output = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(output, dict):
        return []
    resolutions = output.get("resolutions")
    if not isinstance(resolutions, list):
        return []
    # JSON schema guarantees structure; cast validated dicts at I/O boundary
    return [item for item in resolutions if isinstance(item, dict)]  # type: ignore[misc]


def _resolve_with_mock(
    candidates: list[NameRoomCandidate],
    known: set[str],
) -> list[NameResolution]:
    resolutions: list[NameResolution] = []
    for c in candidates:
        key_a = normalize_alias_name(c.name_a)
        key_b = normalize_alias_name(c.name_b)
        inqs_a = c.aliases_by_name.get(key_a) or _lookup_global(
            key_a, c.aliases_by_name_global,
        )
        inqs_b = c.aliases_by_name.get(key_b) or _lookup_global(
            key_b, c.aliases_by_name_global,
        )
        if len(inqs_a) != 1 or len(inqs_b) != 1:
            continue
        inq_a = next(iter(inqs_a))
        inq_b = next(iter(inqs_b))
        if inq_a == inq_b or inq_a not in known or inq_b not in known:
            continue
        resolutions.append({
            "candidate_id": c.candidate_id,
            "inquiry_a": inq_a,
            "inquiry_b": inq_b,
            "room_type": c.room_type,
            "confidence": 0.9,
        })
    return resolutions


def resolve_name_candidates_with_llm(
    candidates: list[NameRoomCandidate],
    llm_provider: str,
    known_output_inquiries: set[str],
) -> list[NameResolution]:
    """Resolve name room candidates via LLM or mock."""
    known = {normalize_inquiry_main(i) for i in known_output_inquiries if i}
    if llm_provider == "mock":
        return _resolve_with_mock(candidates, known)
    if llm_provider == "openai":
        return _resolve_with_openai(candidates, known)
    return []
