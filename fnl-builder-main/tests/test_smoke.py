from __future__ import annotations

import fnl_builder
from fnl_builder.llm.adapter import MockAdapter, NullAdapter, PromptConfig
from fnl_builder.shared.errors import FnlError, InputError, LLMError, ParseError
from fnl_builder.shared.types import Category, LLMItem, Phase


def test_import() -> None:
    assert fnl_builder is not None


def test_errors_hierarchy() -> None:
    assert issubclass(InputError, FnlError)
    assert issubclass(ParseError, FnlError)
    assert issubclass(LLMError, FnlError)


def test_null_adapter() -> None:
    adapter = NullAdapter()
    prompts = PromptConfig(system="sys", extract_base="base")

    assert adapter.extract_remarks("text", [], prompts) == []


def test_mock_adapter() -> None:
    item = LLMItem(
        category=Category.OTHER,
        who_id="guest-1",
        confidence=0.9,
        phase=Phase.EXTRACT,
        handoff_text="handoff",
        evidence_quote="quote",
    )
    adapter = MockAdapter([item])
    prompts = PromptConfig(system="sys", extract_base="base")

    assert adapter.extract_remarks("text", [], prompts) == [item]
