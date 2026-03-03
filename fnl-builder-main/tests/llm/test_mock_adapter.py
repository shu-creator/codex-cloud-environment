"""Tests for the extended mock adapter."""
from __future__ import annotations

from fnl_builder.llm.adapter import PromptConfig
from fnl_builder.llm.mock import FullMockAdapter, _REQUIRED_PHRASES
from fnl_builder.shared.types import Category, LLMItem, Phase


def _prompts() -> PromptConfig:
    return PromptConfig(system="sys", extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}")


class TestFullMockAdapterProtocol:
    def test_extract_remarks_returns_list(self) -> None:
        adapter = FullMockAdapter()
        result = adapter.extract_remarks("text", [(1, "page1")], _prompts())
        assert isinstance(result, list)
        assert all(isinstance(item, LLMItem) for item in result)

class TestFullMockAdapterItems:
    def test_returns_required_phrase_count(self) -> None:
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "some content")], _prompts())
        assert len(items) == len(_REQUIRED_PHRASES)

    def test_required_phrases_summaries(self) -> None:
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "content")], _prompts())
        summaries = {item.summary for item in items}
        expected = {phrase[3] for phrase in _REQUIRED_PHRASES}
        assert summaries == expected

    def test_categories_mapped(self) -> None:
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "content")], _prompts())
        # medical_health → MEDICAL
        medical_items = [it for it in items if it.summary == "医療対応が必要"]
        assert len(medical_items) == 1
        assert medical_items[0].category == Category.MEDICAL

    def test_phases_mapped(self) -> None:
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "content")], _prompts())
        # pre_departure → PRE_DEPARTURE
        pre_dep = [it for it in items if it.summary == "医療対応が必要"]
        assert pre_dep[0].phase == Phase.PRE_DEPARTURE

    def test_who_id_empty(self) -> None:
        """LLM items should not have who_id set (assigned later by pipeline)."""
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "content")], _prompts())
        assert all(item.who_id == "" for item in items)

    def test_phrase_found_in_text(self) -> None:
        """When a required phrase exists in page text, it becomes the evidence quote."""
        adapter = FullMockAdapter()
        items = adapter.extract_remarks(
            "text",
            [(1, "Header1\nHeader2\nインシュリンの件について対応\n")],
            _prompts(),
        )
        insulin_items = [it for it in items if it.summary == "医療対応が必要"]
        assert insulin_items[0].evidence_quote == "インシュリンの件"
        assert insulin_items[0].evidence_page == 1

    def test_fallback_quote_when_phrase_missing(self) -> None:
        """When phrase is not in text, a fallback candidate quote is used."""
        adapter = FullMockAdapter()
        page_text = "Header1\nHeader2\n田中太郎 0067368202-001\n車椅子が必要\n"
        items = adapter.extract_remarks("text", [(1, page_text)], _prompts())
        # None of the required phrases are in this text,
        # so fallback candidates should be used
        for item in items:
            assert item.evidence_quote  # Should have some quote

    def test_confidence_value(self) -> None:
        adapter = FullMockAdapter()
        items = adapter.extract_remarks("text", [(1, "content")], _prompts())
        assert all(item.confidence == 0.7 for item in items)


class TestConfigMockProvider:
    def test_mock_provider_uses_full_mock(self) -> None:
        from fnl_builder.config import PipelineConfig, RunState

        config = PipelineConfig(llm_provider="mock")
        state = RunState.from_config(config)
        assert isinstance(state.llm, FullMockAdapter)
