"""Auto-chunking for large message lists that exceed LLM prompt limits."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from fnl_builder.llm.adapter import LLMAdapter, PromptConfig
from fnl_builder.llm.extraction import LLMExtractionResult, build_user_prompt, extract_items
from fnl_builder.shared.types import LLMItem

_DEFAULT_MAX_PROMPT_CHARS = 120_000
_DEFAULT_MAX_PAGES = 20
_DEFAULT_MAX_CONCURRENCY = 2


@dataclass
class ChunkTask:
    """A chunk of pages to send to the LLM."""

    pages: list[tuple[int, str]]
    start_index: int


def _parse_positive_int_env(raw: str | None, default: int, *, min_value: int = 1) -> int:
    if raw is None:
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed >= min_value else default


def _load_chunk_limits() -> tuple[int, int, int]:
    max_prompt = _parse_positive_int_env(
        os.getenv("FNL_LLM_CHUNK_MAX_PROMPT_CHARS"), _DEFAULT_MAX_PROMPT_CHARS,
    )
    max_pages = _parse_positive_int_env(
        os.getenv("FNL_LLM_CHUNK_MAX_PAGES"), _DEFAULT_MAX_PAGES,
    )
    max_concurrency = _parse_positive_int_env(
        os.getenv("FNL_LLM_CHUNK_MAX_CONCURRENCY"), _DEFAULT_MAX_CONCURRENCY,
    )
    return max_prompt, max_pages, max_concurrency


def _estimate_prompt_chars(
    pages: list[tuple[int, str]],
    prompts: PromptConfig,
    taxonomy_yaml: str,
) -> int:
    user_prompt = build_user_prompt(taxonomy_yaml, pages, prompts.extract_base)
    system = prompts.system
    if prompts.course_supplement:
        system = f"{system}\n\n## コース固有指示\n{prompts.course_supplement}"
    return len(system) + len(user_prompt)


def build_initial_chunk_tasks(
    pages: list[tuple[int, str]],
    prompts: PromptConfig,
    taxonomy_yaml: str,
    max_prompt_chars: int,
    max_pages: int,
) -> list[ChunkTask]:
    """Greedy binning of pages into chunks respecting size limits."""
    tasks: list[ChunkTask] = []
    current: list[tuple[int, str]] = []
    current_start = 0

    for idx, page in enumerate(pages):
        candidate = current + [page]
        exceeds_pages = len(candidate) > max_pages
        exceeds_prompt = False
        if current:
            exceeds_prompt = (
                _estimate_prompt_chars(candidate, prompts, taxonomy_yaml) > max_prompt_chars
            )
        if current and (exceeds_pages or exceeds_prompt):
            tasks.append(ChunkTask(pages=current, start_index=current_start))
            current = [page]
            current_start = idx
        else:
            if not current:
                current_start = idx
            current = candidate

    if current:
        tasks.append(ChunkTask(pages=current, start_index=current_start))
    return tasks


def _is_size_error(result: LLMExtractionResult) -> bool:
    """Check if extraction failed due to HTTP 413 or similar size error."""
    if result.success:
        return False
    return result.error_code == "LLM_SIZE_ERROR"


def _split_chunk(task: ChunkTask) -> tuple[ChunkTask, ChunkTask] | None:
    """Binary split a chunk task. Returns None if unsplittable."""
    if len(task.pages) <= 1:
        return None
    mid = len(task.pages) // 2
    left = ChunkTask(pages=task.pages[:mid], start_index=task.start_index)
    right = ChunkTask(pages=task.pages[mid:], start_index=task.start_index + mid)
    return left, right


def _run_chunk_round(
    tasks: list[ChunkTask],
    adapter: LLMAdapter,
    prompts: PromptConfig,
    taxonomy_yaml: str,
    max_concurrency: int,
) -> tuple[list[tuple[int, list[LLMItem]]], list[tuple[ChunkTask, LLMExtractionResult]]]:
    """Execute one round of chunk extractions concurrently."""
    successes: list[tuple[int, list[LLMItem]]] = []
    failures: list[tuple[ChunkTask, LLMExtractionResult]] = []

    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        future_to_task = {
            executor.submit(
                extract_items, adapter, prompts, task.pages, taxonomy_yaml,
            ): task
            for task in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                result = future.result()
            except Exception:
                result = LLMExtractionResult(
                    items=[], success=False,
                    error_code="LLM_FAILED", error_message="chunk extraction failed",
                )
            if result.success:
                successes.append((task.start_index, result.items))
            else:
                failures.append((task, result))

    return successes, failures


def _handle_failures(
    failures: list[tuple[ChunkTask, LLMExtractionResult]],
    retry_queue: list[ChunkTask],
) -> LLMExtractionResult | None:
    """Process failures: split size errors, return first non-recoverable failure."""
    for task, result in failures:
        if _is_size_error(result):
            split = _split_chunk(task)
            if split is not None:
                retry_queue.extend(split)
                continue
        return result
    return None


def run_chunked_extraction(
    adapter: LLMAdapter,
    pages: list[tuple[int, str]],
    prompts: PromptConfig,
    taxonomy_yaml: str,
) -> LLMExtractionResult:
    """Run LLM extraction with auto-chunking for large inputs.

    Small inputs (within limits) are processed as a single chunk.
    On HTTP 413, chunks are binary-split and retried.
    """
    max_prompt, max_pages, max_concurrency = _load_chunk_limits()
    queue = build_initial_chunk_tasks(pages, prompts, taxonomy_yaml, max_prompt, max_pages)

    if not queue:
        return LLMExtractionResult(items=[], success=True)

    all_items: list[tuple[int, list[LLMItem]]] = []

    while queue:
        round_tasks = queue
        queue = []
        successes, failures = _run_chunk_round(
            round_tasks, adapter, prompts, taxonomy_yaml, max_concurrency,
        )
        all_items.extend(successes)

        if failures:
            terminal = _handle_failures(failures, queue)
            if terminal is not None:
                return terminal

    merged = [item for _, items in sorted(all_items) for item in items]
    return LLMExtractionResult(items=merged, success=True)


def needs_chunking(
    pages: list[tuple[int, str]],
    prompts: PromptConfig,
    taxonomy_yaml: str,
) -> bool:
    """Check whether the input exceeds chunk limits and requires splitting."""
    max_prompt, max_pages, _ = _load_chunk_limits()
    if len(pages) > max_pages:
        return True
    return _estimate_prompt_chars(pages, prompts, taxonomy_yaml) > max_prompt
