"""Tests for tour header rule+LLM fallback chain."""
from __future__ import annotations

from fnl_builder.llm.adapter import MockAdapter, NullAdapter
from fnl_builder.parse.tour_header_llm import extract_tour_header
from fnl_builder.shared.types import Issue, TourHeaderData


class _FakeLLMAdapter:
    """Test adapter that returns a fixed TourHeaderData."""

    def __init__(self, result: TourHeaderData | None) -> None:
        self._result = result
        self.called = False
        self.last_excerpt = ""

    def extract_remarks(self, text: str, pages: list[object], prompts: object) -> list[object]:
        return []

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        self.called = True
        self.last_excerpt = excerpt
        return self._result

    def resolve_room_merge(self, candidates: list[object]) -> list[object]:
        return []


class _FailingLLMAdapter:
    """Test adapter that raises an exception."""

    def extract_remarks(self, text: str, pages: list[object], prompts: object) -> list[object]:
        return []

    def extract_tour_header(self, excerpt: str) -> TourHeaderData | None:
        raise RuntimeError("LLM connection failed")

    def resolve_room_merge(self, candidates: list[object]) -> list[object]:
        return []


_RL_WITH_HEADER = """\
ROOMING LIST
E417 26-10-08 ~ 26-10-15
E417 NRT TYO SPAIN PORTUGAL 8DAYS
TOTAL 20名
"""

_RL_NO_HEADER = """\
Some random text with no matching info
Just guest names and data
"""


class TestExtractTourHeader:
    def test_rule_based_success(self) -> None:
        issues: list[Issue] = []
        result = extract_tour_header(_RL_WITH_HEADER, NullAdapter(), issues)
        assert result.tour_ref == "E417 1008"
        assert result.confidence == 0.95
        assert not issues

    def test_rule_based_success_skips_llm(self) -> None:
        adapter = _FakeLLMAdapter(TourHeaderData(tour_ref="X999 0101", confidence=0.8))
        issues: list[Issue] = []
        result = extract_tour_header(_RL_WITH_HEADER, adapter, issues)
        assert result.tour_ref == "E417 1008"
        assert not adapter.called

    def test_no_header_lines_returns_empty(self) -> None:
        adapter = _FakeLLMAdapter(TourHeaderData(tour_ref="X999 0101", confidence=0.8))
        issues: list[Issue] = []
        result = extract_tour_header(_RL_NO_HEADER, adapter, issues)
        # No header-relevant lines → empty excerpt → LLM not called
        assert result == TourHeaderData.empty()
        assert not adapter.called

    def test_llm_called_with_excerpt(self) -> None:
        # Text with TOUR keyword but no regex match for course/date
        rl_text = "TOUR NAME: Unknown Format\nTOTAL 10名\n"
        expected = TourHeaderData(tour_ref="A100 0501", confidence=0.85)
        adapter = _FakeLLMAdapter(expected)
        issues: list[Issue] = []
        result = extract_tour_header(rl_text, adapter, issues)
        assert result == expected
        assert adapter.called
        assert "TOUR NAME" in adapter.last_excerpt

    def test_null_adapter_returns_empty(self) -> None:
        issues: list[Issue] = []
        result = extract_tour_header(_RL_NO_HEADER, NullAdapter(), issues)
        assert result == TourHeaderData.empty()
        assert not issues

    def test_llm_returns_none(self) -> None:
        adapter = _FakeLLMAdapter(None)
        rl_text = "TOUR NAME: Unknown\nTOTAL 5名\n"
        issues: list[Issue] = []
        result = extract_tour_header(rl_text, adapter, issues)
        assert result == TourHeaderData.empty()

    def test_llm_exception_records_warning(self) -> None:
        rl_text = "TOUR NAME: Unknown\nTOTAL 5名\n"
        issues: list[Issue] = []
        result = extract_tour_header(rl_text, _FailingLLMAdapter(), issues)  # type: ignore[arg-type]
        assert result == TourHeaderData.empty()
        assert len(issues) == 1
        assert issues[0].level == "warning"
        assert issues[0].code == "tour_header_llm_failed"

    def test_mock_adapter_has_extract_tour_header(self) -> None:
        adapter = MockAdapter(items=[])
        result = adapter.extract_tour_header("some excerpt")
        assert result is None
