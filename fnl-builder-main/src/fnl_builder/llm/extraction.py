"""LLM extraction stage: build prompts, call adapter, parse results."""
from __future__ import annotations

import json
import socket
import urllib.error
from dataclasses import dataclass

from fnl_builder.llm.adapter import LLMAdapter, PromptConfig
from fnl_builder.llm.prompt_loader import load_prompts, load_taxonomy
from fnl_builder.shared.errors import LLMError
from fnl_builder.shared.types import Issue, LLMItem


@dataclass(frozen=True)
class LLMExtractionResult:
    """Result of an LLM extraction pass."""

    items: list[LLMItem]
    success: bool
    error_code: str = ""
    error_message: str = ""


def build_user_prompt(
    taxonomy_yaml: str,
    pages: list[tuple[int, str]],
    template: str,
    extra_note: str | None = None,
) -> str:
    """Build user prompt by filling template placeholders.

    Args:
        taxonomy_yaml: YAML text for category/phase taxonomy.
        pages: List of (page_number, page_text) tuples.
        template: Prompt template with ``{{TAXONOMY_YAML}}`` and ``{{PAGES_TEXT}}``.
        extra_note: Optional note prepended to the prompt (e.g. pass-2 instructions).
    """
    page_lines: list[str] = []
    for page_no, text in pages:
        page_lines.append(f"[page {page_no}]\n{text}")
    pages_text = "\n\n".join(page_lines)

    prompt = template.replace("{{TAXONOMY_YAML}}", taxonomy_yaml).replace(
        "{{PAGES_TEXT}}", pages_text
    )
    if extra_note:
        prompt = f"{extra_note}\n\n{prompt}"
    return prompt


def classify_llm_error(exc: Exception) -> tuple[str, bool]:
    """Classify an exception into (error_code, retriable).

    Error codes:
        LLM_PARSE_FAILED  — malformed JSON / missing keys (non-retriable)
        LLM_AUTH_FAILED   — 401/403 or missing API key (non-retriable)
        LLM_TIMEOUT       — 429 rate limit or socket timeout (retriable)
        LLM_FAILED        — other failures (retriable if 5xx)
    """
    if isinstance(exc, (json.JSONDecodeError, KeyError, IndexError, ValueError)):
        return "LLM_PARSE_FAILED", False

    if isinstance(exc, urllib.error.HTTPError):
        status = int(exc.code)
        if status in (401, 403):
            return "LLM_AUTH_FAILED", False
        if status == 413:
            return "LLM_SIZE_ERROR", False
        if status == 429:
            return "LLM_TIMEOUT", True
        return "LLM_FAILED", 500 <= status <= 599

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return "LLM_TIMEOUT", True
        return "LLM_FAILED", True

    if isinstance(exc, TimeoutError):
        return "LLM_TIMEOUT", True

    if isinstance(exc, LLMError):
        # Check wrapped cause for HTTP 413
        cause = exc.__cause__
        if isinstance(cause, urllib.error.HTTPError) and cause.code == 413:
            return "LLM_SIZE_ERROR", False
        msg = str(exc).lower()
        if "413" in msg:
            return "LLM_SIZE_ERROR", False
        if "api_key" in msg or "auth" in msg:
            return "LLM_AUTH_FAILED", False
        if "parse" in msg:
            return "LLM_PARSE_FAILED", False
        return "LLM_FAILED", False

    return "LLM_FAILED", False


def _item_merge_key(item: LLMItem) -> tuple[str, str, int | None, str] | None:
    """Compute dedup key for an LLM item."""
    if not item.category or not item.phase or not item.evidence_quote:
        return None
    return (item.category.value, item.phase.value, item.evidence_page, item.evidence_quote)


def merge_items(first: list[LLMItem], second: list[LLMItem]) -> list[LLMItem]:
    """Merge two item lists, deduplicating by (category, phase, page, quote)."""
    merged: list[LLMItem] = []
    seen: set[tuple[str, str, int | None, str]] = set()
    for item in [*first, *second]:
        key = _item_merge_key(item)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        merged.append(item)
    return merged


def sort_items_by_page(items: list[LLMItem]) -> list[LLMItem]:
    """Sort items by evidence page number (missing pages last)."""
    return sorted(items, key=lambda it: it.evidence_page if it.evidence_page is not None else 10**9)


def extract_items(
    adapter: LLMAdapter,
    prompts: PromptConfig,
    pages: list[tuple[int, str]],
    taxonomy_yaml: str,
    *,
    extra_note: str | None = None,
) -> LLMExtractionResult:
    """Run a single extraction pass via the LLM adapter.

    Builds the user prompt, calls the adapter, and wraps errors.
    """
    user_prompt = build_user_prompt(
        taxonomy_yaml=taxonomy_yaml,
        pages=pages,
        template=prompts.extract_base,
        extra_note=extra_note,
    )
    try:
        items = adapter.extract_remarks(user_prompt, list(pages), prompts)
        return LLMExtractionResult(items=items, success=True)
    except (LLMError, Exception) as exc:
        code, _ = classify_llm_error(exc)
        return LLMExtractionResult(
            items=[],
            success=False,
            error_code=code,
            error_message=str(exc),
        )


_PASS2_NOTE = (
    "この呼び出しは未抽出ページのみの再スキャンです。"
    "該当する内容があれば漏れなく抽出してください。"
    "該当なしの場合は空配列 [] を返してください。"
)


def run_llm_extraction(
    adapter: LLMAdapter,
    pages: list[tuple[int, str]],
    course_codes: list[str] | None = None,
    issues: list[Issue] | None = None,
) -> tuple[list[LLMItem], bool]:
    """Run full LLM extraction (pass 1 + optional pass 2).

    For large inputs exceeding chunk limits, auto-chunking is used instead
    of the standard 2-pass approach.

    Returns:
        (items, success) — merged item list and overall success flag.
    """
    if issues is None:
        issues = []

    prompts = load_prompts(course_codes)
    taxonomy_yaml = load_taxonomy()

    # --- Auto-chunking for large inputs ---
    from fnl_builder.llm.chunking import needs_chunking, run_chunked_extraction

    if needs_chunking(pages, prompts, taxonomy_yaml):
        chunk_result = run_chunked_extraction(adapter, pages, prompts, taxonomy_yaml)
        if not chunk_result.success:
            issues.append(
                Issue(
                    level="warning",
                    code="llm_chunked_extraction_failed",
                    message=f"Chunked LLM extraction failed: {chunk_result.error_code}"
                    f" — {chunk_result.error_message}",
                )
            )
            return [], False
        return sort_items_by_page(chunk_result.items), True

    # --- Pass 1 (standard path for small inputs) ---
    result1 = extract_items(adapter, prompts, pages, taxonomy_yaml)

    if not result1.success:
        issues.append(
            Issue(
                level="warning",
                code="llm_extraction_failed",
                message=f"LLM pass 1 failed: {result1.error_code} — {result1.error_message}",
            )
        )
        return [], False

    # Determine pages with extracted items
    pages_with_items = {it.evidence_page for it in result1.items if it.evidence_page is not None}
    all_page_nums = {p for p, _ in pages}
    missing_pages = all_page_nums - pages_with_items

    if not missing_pages:
        return sort_items_by_page(result1.items), True

    # --- Pass 2: re-scan missing pages ---
    pass2_pages = [(p, t) for p, t in pages if p in missing_pages]
    result2 = extract_items(
        adapter, prompts, pass2_pages, taxonomy_yaml, extra_note=_PASS2_NOTE,
    )

    if not result2.success:
        issues.append(
            Issue(
                level="info",
                code="llm_pass2_failed",
                message=f"LLM pass 2 failed (non-critical): {result2.error_code}",
            )
        )
        return sort_items_by_page(result1.items), True

    merged = merge_items(result1.items, result2.items)
    return sort_items_by_page(merged), True
