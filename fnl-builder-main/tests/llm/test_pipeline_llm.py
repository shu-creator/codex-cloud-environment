"""Tests for LLM integration in pipeline."""
from __future__ import annotations

from fnl_builder.config import PipelineConfig, RunState
from fnl_builder.integrate.p_markers import assign_initial_who_id
from fnl_builder.llm.adapter import NullAdapter
from fnl_builder.pipeline import _build_llm_dicts, _run_llm_stage
from fnl_builder.shared.types import Category, GuestRecord, InquiryKey, Issue, LLMItem, Phase


def _item(
    *,
    who_id: str = "",
    category: Category = Category.MEDICAL,
    handoff_text: str = "Handle it",
) -> LLMItem:
    return LLMItem(
        category=category,
        who_id=who_id,
        confidence=0.9,
        phase=Phase.ON_TOUR,
        handoff_text=handoff_text,
        evidence_quote="quote",
        summary="summary",
        evidence_page=1,
    )


def _guest(inquiry_main: str = "12345678", branch: str | None = None) -> GuestRecord:
    return GuestRecord(
        inquiry=InquiryKey(main=inquiry_main, branch=branch),
        full_name="TEST USER",
        family_name="TEST",
        given_name="USER",
    )


class TestBuildLlmDicts:
    def test_empty_items(self) -> None:
        notes, items_dict = _build_llm_dicts([], [])
        assert notes == {}
        assert items_dict == {}

    def test_items_without_who_id(self) -> None:
        items = [_item(who_id="")]
        notes, items_dict = _build_llm_dicts(items, [])
        assert ("", "0") in notes
        assert ("", "0") in items_dict
        assert len(items_dict[("", "0")]) == 1

    def test_items_distributed_to_all_positions(self) -> None:
        # Two guests under same inquiry → item distributed to both
        guests = [_guest("67368202"), _guest("67368202")]
        items = [_item(who_id="0067368202-001")]
        notes, items_dict = _build_llm_dicts(items, guests)
        assert ("67368202", "1") in items_dict
        assert ("67368202", "2") in items_dict

    def test_items_with_unresolvable_who_id(self) -> None:
        items = [_item(who_id="INVALID")]
        notes, items_dict = _build_llm_dicts(items, [])
        assert ("", "0") in notes

    def test_notes_formatted(self) -> None:
        items = [_item(category=Category.MEDICAL, handoff_text="Wheelchair needed")]
        notes, _ = _build_llm_dicts(items, [])
        assert "[MEDICAL] Wheelchair needed" in notes[("", "0")]

    def test_empty_handoff_no_note(self) -> None:
        items = [_item(handoff_text="")]
        notes, items_dict = _build_llm_dicts(items, [])
        assert notes[("", "0")] == []
        assert len(items_dict[("", "0")]) == 1

    def test_dedup_notes(self) -> None:
        items = [_item(handoff_text="Same"), _item(handoff_text="Same")]
        notes, _ = _build_llm_dicts(items, [])
        assert len(notes[("", "0")]) == 1


class TestRunLlmStage:
    def test_null_adapter_returns_empty(self) -> None:
        config = PipelineConfig(llm_provider="none")
        state = RunState.from_config(config)
        notes, items_dict, success, raw_count = _run_llm_stage(state, [], None, [])
        assert notes == {}
        assert items_dict == {}
        assert success is False
        assert raw_count == 0

    def test_adapter_selection_none(self) -> None:
        config = PipelineConfig(llm_provider="none")
        state = RunState.from_config(config)
        assert isinstance(state.llm, NullAdapter)


class TestConfigAdapterSelection:
    def test_none_provider(self) -> None:
        config = PipelineConfig(llm_provider="none")
        state = RunState.from_config(config)
        assert isinstance(state.llm, NullAdapter)

    def test_mock_provider(self) -> None:
        from fnl_builder.llm.mock import FullMockAdapter

        config = PipelineConfig(llm_provider="mock")
        state = RunState.from_config(config)
        assert isinstance(state.llm, FullMockAdapter)

    def test_openai_provider(self) -> None:
        from fnl_builder.llm.openai import OpenAIAdapter

        config = PipelineConfig(llm_provider="openai")
        state = RunState.from_config(config)
        assert isinstance(state.llm, OpenAIAdapter)


class TestAssignInitialWhoId:
    def test_assigns_who_id_from_participant_line(self) -> None:
        """Item without who_id gets assigned based on nearest participant above quote."""
        page_text = "田中太郎 0067368202-001\n車椅子が必要です\n"
        pages = [(1, page_text)]
        items = [
            LLMItem(
                category=Category.MEDICAL,
                who_id="",
                confidence=0.9,
                phase=Phase.ON_TOUR,
                handoff_text="Wheelchair",
                evidence_quote="車椅子が必要です",
                summary="summary",
                evidence_page=1,
            )
        ]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, pages, issues)
        assert len(result) == 1
        assert result[0].who_id == "67368202-001"

    def test_preserves_existing_who_id(self) -> None:
        items = [_item(who_id="99999999-001")]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, [(1, "text")], issues)
        assert result[0].who_id == "99999999-001"

    def test_preassigned_who_id_skipped(self) -> None:
        items = [_item(who_id="0067621009-001")]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, [(1, "text")], issues)
        assert result[0].who_id == "0067621009-001"

    def test_unresolved_when_no_participants(self) -> None:
        """Page without participant lines → item stays unresolved."""
        pages = [(1, "何かのテキスト\n")]
        items = [_item(who_id="")]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, pages, issues)
        assert result[0].who_id == ""
        assert any("llm_who_id_unresolved" in i.code for i in issues)

    def test_no_evidence_page(self) -> None:
        items = [
            LLMItem(
                category=Category.MEDICAL,
                who_id="",
                confidence=0.9,
                phase=Phase.ON_TOUR,
                handoff_text="text",
                evidence_quote="q",
                summary="s",
                evidence_page=None,
            )
        ]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, [(1, "text")], issues)
        assert result[0].who_id == ""

    def test_multiple_participants_nearest_above(self) -> None:
        """With two participants, item is assigned to the one above the quote."""
        page_text = (
            "田中太郎 0067368202-001\n"
            "田中の備考テキスト\n"
            "佐藤花子 0067368202-002\n"
            "佐藤の備考テキスト\n"
        )
        pages = [(1, page_text)]
        items = [
            LLMItem(
                category=Category.MEDICAL,
                who_id="",
                confidence=0.9,
                phase=Phase.ON_TOUR,
                handoff_text="text",
                evidence_quote="佐藤の備考テキスト",
                summary="s",
                evidence_page=1,
            )
        ]
        issues: list[Issue] = []
        result = assign_initial_who_id(items, pages, issues)
        assert result[0].who_id == "67368202-002"

    def test_empty_items_returns_empty(self) -> None:
        issues: list[Issue] = []
        result = assign_initial_who_id([], [(1, "text")], issues)
        assert result == []
