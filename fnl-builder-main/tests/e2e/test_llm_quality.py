"""LLM prompt regression tests.

Run with: pytest -m llm_quality

These tests verify that the LLM extraction pipeline produces expected
results with known input data. They use FullMockAdapter by default
but can be pointed at a real LLM provider via --llm-provider flag
in a future phase.
"""
from __future__ import annotations

import pytest

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.mock import FullMockAdapter, _REQUIRED_PHRASES
from fnl_builder.shared.types import LLMItem


@pytest.mark.llm_quality
class TestLlmQualityBaseline:
    """Baseline quality checks using FullMockAdapter."""

    def test_all_required_phrases_present(self) -> None:
        adapter = FullMockAdapter()
        prompts = PromptConfig(
            system="sys",
            extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}",
        )
        pages: list[tuple[int, str]] = [(1, "sample text")]
        items = adapter.extract_remarks("text", list(pages), prompts)

        expected_summaries = {phrase[3] for phrase in _REQUIRED_PHRASES}
        actual_summaries = {item.summary for item in items}
        assert expected_summaries == actual_summaries

    def test_items_are_valid_llm_items(self) -> None:
        adapter = FullMockAdapter()
        prompts = PromptConfig(
            system="sys",
            extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}",
        )
        items = adapter.extract_remarks("text", [(1, "text")], prompts)
        for item in items:
            assert isinstance(item, LLMItem)
            assert item.category is not None
            assert item.phase is not None
            assert item.summary
            assert item.handoff_text
            assert 0 <= item.confidence <= 1


@pytest.mark.llm_quality
class TestLlmQualityMarker:
    """Verify the llm_quality marker is registered and selectable."""

    def test_marker_registered(self) -> None:
        # This test existing confirms the marker is registered
        # (would fail with PytestUnknownMarkWarning otherwise)
        pass
