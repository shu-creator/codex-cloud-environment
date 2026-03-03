"""Tests for LLM extraction stage."""
from __future__ import annotations

import json

from fnl_builder.llm.adapter import MockAdapter, NullAdapter, PromptConfig
from fnl_builder.llm.extraction import (
    build_user_prompt,
    classify_llm_error,
    extract_items,
    merge_items,
    run_llm_extraction,
    sort_items_by_page,
)
from fnl_builder.shared.errors import LLMError
from fnl_builder.shared.types import Category, Issue, LLMItem, Phase


def _item(
    *,
    category: Category = Category.MEDICAL,
    phase: Phase = Phase.ON_TOUR,
    who_id: str = "",
    confidence: float = 0.9,
    handoff_text: str = "Handle it",
    evidence_quote: str = "quote",
    summary: str = "Summary",
    evidence_page: int | None = 1,
) -> LLMItem:
    return LLMItem(
        category=category,
        who_id=who_id,
        confidence=confidence,
        phase=phase,
        handoff_text=handoff_text,
        evidence_quote=evidence_quote,
        summary=summary,
        evidence_page=evidence_page,
    )


class TestBuildUserPrompt:
    def test_replaces_placeholders(self) -> None:
        template = "Taxonomy:\n{{TAXONOMY_YAML}}\n\nPages:\n{{PAGES_TEXT}}"
        result = build_user_prompt(
            taxonomy_yaml="categories: [a, b]",
            pages=[(1, "Page one text"), (2, "Page two text")],
            template=template,
        )
        assert "categories: [a, b]" in result
        assert "[page 1]\nPage one text" in result
        assert "[page 2]\nPage two text" in result

    def test_extra_note_prepended(self) -> None:
        result = build_user_prompt(
            taxonomy_yaml="yaml",
            pages=[(1, "text")],
            template="{{TAXONOMY_YAML}} {{PAGES_TEXT}}",
            extra_note="Extra instructions",
        )
        assert result.startswith("Extra instructions\n\n")

    def test_no_extra_note(self) -> None:
        result = build_user_prompt(
            taxonomy_yaml="yaml",
            pages=[(1, "text")],
            template="{{TAXONOMY_YAML}} {{PAGES_TEXT}}",
        )
        assert not result.startswith("Extra")

    def test_empty_pages(self) -> None:
        result = build_user_prompt(
            taxonomy_yaml="yaml",
            pages=[],
            template="T:{{TAXONOMY_YAML}} P:{{PAGES_TEXT}}",
        )
        assert "P:" in result


class TestClassifyLlmError:
    def test_json_decode_error(self) -> None:
        code, retriable = classify_llm_error(json.JSONDecodeError("msg", "doc", 0))
        assert code == "LLM_PARSE_FAILED"
        assert retriable is False

    def test_value_error(self) -> None:
        code, retriable = classify_llm_error(ValueError("bad"))
        assert code == "LLM_PARSE_FAILED"
        assert retriable is False

    def test_timeout_error(self) -> None:
        code, retriable = classify_llm_error(TimeoutError("timeout"))
        assert code == "LLM_TIMEOUT"
        assert retriable is True

    def test_llm_error_auth(self) -> None:
        code, retriable = classify_llm_error(LLMError("OPENAI_API_KEY is required"))
        assert code == "LLM_AUTH_FAILED"
        assert retriable is False

    def test_llm_error_parse(self) -> None:
        code, retriable = classify_llm_error(LLMError("Failed to parse LLM response"))
        assert code == "LLM_PARSE_FAILED"
        assert retriable is False

    def test_llm_error_generic(self) -> None:
        code, retriable = classify_llm_error(LLMError("OpenAI API error: 500"))
        assert code == "LLM_FAILED"
        assert retriable is False

    def test_http_413_size_error(self) -> None:
        import urllib.error
        exc = urllib.error.HTTPError("url", 413, "Too Large", {}, None)  # type: ignore[arg-type]
        code, retriable = classify_llm_error(exc)
        assert code == "LLM_SIZE_ERROR"
        assert retriable is False

    def test_llm_error_wrapping_413(self) -> None:
        import urllib.error
        cause = urllib.error.HTTPError("url", 413, "Too Large", {}, None)  # type: ignore[arg-type]
        wrapped = LLMError("OpenAI API error: HTTP Error 413")
        wrapped.__cause__ = cause
        code, retriable = classify_llm_error(wrapped)
        assert code == "LLM_SIZE_ERROR"
        assert retriable is False

    def test_llm_error_413_in_message(self) -> None:
        code, retriable = classify_llm_error(LLMError("OpenAI API error: 413"))
        assert code == "LLM_SIZE_ERROR"
        assert retriable is False

    def test_unknown_error(self) -> None:
        code, retriable = classify_llm_error(RuntimeError("unknown"))
        assert code == "LLM_FAILED"
        assert retriable is False


class TestMergeItems:
    def test_no_duplicates(self) -> None:
        a = [_item(evidence_page=1, evidence_quote="q1")]
        b = [_item(evidence_page=2, evidence_quote="q2")]
        merged = merge_items(a, b)
        assert len(merged) == 2

    def test_dedup_by_key(self) -> None:
        item = _item(evidence_page=1, evidence_quote="q1")
        merged = merge_items([item], [item])
        assert len(merged) == 1

    def test_different_category_not_deduped(self) -> None:
        a = _item(category=Category.MEDICAL, evidence_page=1, evidence_quote="q")
        b = _item(category=Category.MEAL, evidence_page=1, evidence_quote="q")
        merged = merge_items([a], [b])
        assert len(merged) == 2

    def test_items_without_quote_kept(self) -> None:
        a = _item(evidence_quote="")
        b = _item(evidence_quote="")
        merged = merge_items([a], [b])
        assert len(merged) == 2  # Both kept (no merge key)

    def test_first_pass_priority(self) -> None:
        a = _item(evidence_page=1, evidence_quote="q", summary="first")
        b = _item(evidence_page=1, evidence_quote="q", summary="second")
        merged = merge_items([a], [b])
        assert len(merged) == 1
        assert merged[0].summary == "first"


class TestSortItemsByPage:
    def test_sorted_order(self) -> None:
        items = [_item(evidence_page=3), _item(evidence_page=1), _item(evidence_page=2)]
        result = sort_items_by_page(items)
        assert [it.evidence_page for it in result] == [1, 2, 3]

    def test_none_page_last(self) -> None:
        items = [_item(evidence_page=None), _item(evidence_page=1)]
        result = sort_items_by_page(items)
        assert result[0].evidence_page == 1
        assert result[1].evidence_page is None


class TestExtractItems:
    def test_success_with_mock(self) -> None:
        items = [_item()]
        adapter = MockAdapter(items=items)
        prompts = PromptConfig(
            system="sys",
            extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}",
        )
        result = extract_items(adapter, prompts, [(1, "text")], "taxonomy")
        assert result.success is True
        assert len(result.items) == 1

    def test_null_adapter_returns_empty(self) -> None:
        adapter = NullAdapter()
        prompts = PromptConfig(system="sys", extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}")
        result = extract_items(adapter, prompts, [(1, "text")], "taxonomy")
        assert result.success is True
        assert result.items == []

    def test_error_captured(self) -> None:
        class FailAdapter:
            def extract_remarks(
                self, text: str, pages: list[object], prompts: PromptConfig
            ) -> list[LLMItem]:
                raise LLMError("API down")

            def resolve_room_merge(self, candidates: list[object]) -> list[object]:
                return []

        adapter = FailAdapter()
        prompts = PromptConfig(system="sys", extract_base="{{TAXONOMY_YAML}} {{PAGES_TEXT}}")
        result = extract_items(adapter, prompts, [(1, "text")], "taxonomy")
        assert result.success is False
        assert result.error_code == "LLM_FAILED"
        assert "API down" in result.error_message


class TestRunLlmExtraction:
    def test_with_mock_adapter(self) -> None:
        items = [_item(evidence_page=1)]
        adapter = MockAdapter(items=items)
        issues: list[Issue] = []
        result_items, success = run_llm_extraction(
            adapter=adapter,
            pages=[(1, "text")],
            issues=issues,
        )
        assert success is True
        assert len(result_items) >= 1

    def test_failure_records_issue(self) -> None:
        class FailAdapter:
            def extract_remarks(
                self, text: str, pages: list[object], prompts: PromptConfig
            ) -> list[LLMItem]:
                raise LLMError("fail")

            def resolve_room_merge(self, candidates: list[object]) -> list[object]:
                return []

        issues: list[Issue] = []
        result_items, success = run_llm_extraction(
            adapter=FailAdapter(),
            pages=[(1, "text")],
            issues=issues,
        )
        assert success is False
        assert result_items == []
        assert any("llm_extraction_failed" in i.code for i in issues)

    def test_pass2_triggered_for_missing_pages(self) -> None:
        # MockAdapter returns items with evidence_page from its fixed list
        # When pages have more page numbers than items cover, pass 2 triggers
        items_p1 = [_item(evidence_page=1)]
        adapter = MockAdapter(items=items_p1)
        issues: list[Issue] = []
        result_items, success = run_llm_extraction(
            adapter=adapter,
            pages=[(1, "p1"), (2, "p2"), (3, "p3")],
            issues=issues,
        )
        assert success is True
        # Pass 2 would have been called for pages 2,3
        # MockAdapter returns same items, so merge deduplicates
