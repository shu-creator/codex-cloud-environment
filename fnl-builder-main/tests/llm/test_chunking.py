"""Tests for LLM auto-chunking module."""
from __future__ import annotations

from fnl_builder.llm.adapter import MockAdapter, PromptConfig
from fnl_builder.llm.chunking import (
    ChunkTask,
    _split_chunk,
    build_initial_chunk_tasks,
    needs_chunking,
    run_chunked_extraction,
)
from fnl_builder.shared.types import Category, LLMItem, Phase


def _prompts() -> PromptConfig:
    return PromptConfig(system="sys", extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}")


def _item(page: int) -> LLMItem:
    return LLMItem(
        category=Category.MEDICAL,
        who_id="",
        confidence=0.9,
        phase=Phase.ON_TOUR,
        handoff_text="test",
        evidence_quote="quote",
        evidence_page=page,
    )


class TestBuildInitialChunkTasks:
    def test_single_page_single_chunk(self) -> None:
        pages = [(1, "text")]
        tasks = build_initial_chunk_tasks(pages, _prompts(), "tax", 999999, 20)
        assert len(tasks) == 1
        assert tasks[0].pages == pages

    def test_exceeds_max_pages(self) -> None:
        pages = [(i, f"page {i}") for i in range(5)]
        tasks = build_initial_chunk_tasks(pages, _prompts(), "tax", 999999, 2)
        assert len(tasks) == 3  # [0,1], [2,3], [4]
        assert len(tasks[0].pages) == 2
        assert len(tasks[1].pages) == 2
        assert len(tasks[2].pages) == 1

    def test_exceeds_max_prompt_chars(self) -> None:
        # Each page has 100 chars, max prompt is 250 (system ~3 + template overhead)
        pages = [(i, "x" * 100) for i in range(5)]
        tasks = build_initial_chunk_tasks(pages, _prompts(), "tax", 250, 100)
        assert len(tasks) > 1

    def test_empty_pages(self) -> None:
        tasks = build_initial_chunk_tasks([], _prompts(), "tax", 999999, 20)
        assert len(tasks) == 0

    def test_start_indices(self) -> None:
        pages = [(i, f"p{i}") for i in range(6)]
        tasks = build_initial_chunk_tasks(pages, _prompts(), "tax", 999999, 2)
        assert tasks[0].start_index == 0
        assert tasks[1].start_index == 2
        assert tasks[2].start_index == 4


class TestSplitChunk:
    def test_split_two_pages(self) -> None:
        task = ChunkTask(pages=[(1, "a"), (2, "b")], start_index=0)
        result = _split_chunk(task)
        assert result is not None
        left, right = result
        assert len(left.pages) == 1
        assert len(right.pages) == 1
        assert right.start_index == 1

    def test_single_page_unsplittable(self) -> None:
        task = ChunkTask(pages=[(1, "a")], start_index=0)
        assert _split_chunk(task) is None

    def test_three_pages_split(self) -> None:
        task = ChunkTask(pages=[(1, "a"), (2, "b"), (3, "c")], start_index=5)
        result = _split_chunk(task)
        assert result is not None
        left, right = result
        assert left.start_index == 5
        assert right.start_index == 6


class TestNeedsChunking:
    def test_small_input(self) -> None:
        assert not needs_chunking([(1, "text")], _prompts(), "tax")

    def test_many_pages(self) -> None:
        pages = [(i, "text") for i in range(25)]
        assert needs_chunking(pages, _prompts(), "tax")


class TestRunChunkedExtraction:
    def test_empty_pages(self) -> None:
        adapter = MockAdapter(items=[])
        result = run_chunked_extraction(adapter, [], _prompts(), "tax")
        assert result.success
        assert result.items == []

    def test_single_chunk_success(self) -> None:
        items = [_item(1)]
        adapter = MockAdapter(items=items)
        result = run_chunked_extraction(
            adapter, [(1, "text")], _prompts(), "tax",
        )
        assert result.success
        assert len(result.items) >= 1

    def test_multiple_chunks(self) -> None:
        items = [_item(1)]
        adapter = MockAdapter(items=items)
        pages = [(i, f"page {i}") for i in range(5)]
        result = run_chunked_extraction(adapter, pages, _prompts(), "tax")
        assert result.success
        # Multiple chunks should each produce items
        assert len(result.items) >= 1

    def test_failure_propagated(self) -> None:
        class FailAdapter:
            def extract_remarks(
                self, text: str, pages: list[object], prompts: PromptConfig,
            ) -> list[LLMItem]:
                raise RuntimeError("fail")

            def resolve_room_merge(self, candidates: list[object]) -> list[object]:
                return []

        result = run_chunked_extraction(
            FailAdapter(), [(1, "text")], _prompts(), "tax",  # type: ignore[arg-type]
        )
        assert not result.success
