"""Tests for LLM/mock name room merge resolver."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_name_llm import resolve_name_candidates_with_llm
from fnl_builder.shared.types import NameRoomCandidate


def _candidate(
    cid: int,
    name_a: str,
    name_b: str,
    aliases: dict[str, set[str]] | None = None,
) -> NameRoomCandidate:
    return NameRoomCandidate(
        candidate_id=cid,
        line_no=1,
        line_text=f"{name_a}と{name_b} 同室",
        name_a=name_a,
        name_b=name_b,
        room_type=None,
        context_inquiry=None,
        aliases_by_name=aliases or {},
        aliases_by_name_global={},
    )


class TestResolveWithMock:
    def test_resolves_with_aliases(self) -> None:
        c = _candidate(1, "TANAKA", "SUZUKI", {
            "TANAKA": {"100"},
            "SUZUKI": {"200"},
        })
        results = resolve_name_candidates_with_llm(
            [c], "mock", {"100", "200"},
        )
        assert len(results) == 1
        assert results[0]["inquiry_a"] == "100"
        assert results[0]["inquiry_b"] == "200"
        assert results[0]["confidence"] == 0.9

    def test_ambiguous_alias_skipped(self) -> None:
        c = _candidate(1, "TANAKA", "SUZUKI", {
            "TANAKA": {"100", "200"},
            "SUZUKI": {"300"},
        })
        results = resolve_name_candidates_with_llm(
            [c], "mock", {"100", "200", "300"},
        )
        assert len(results) == 0

    def test_unknown_inquiry_skipped(self) -> None:
        c = _candidate(1, "TANAKA", "SUZUKI", {
            "TANAKA": {"100"},
            "SUZUKI": {"999"},
        })
        results = resolve_name_candidates_with_llm(
            [c], "mock", {"100", "200"},
        )
        assert len(results) == 0


class TestResolveWithNone:
    def test_none_provider_returns_empty(self) -> None:
        c = _candidate(1, "TANAKA", "SUZUKI")
        results = resolve_name_candidates_with_llm([c], "none", {"100"})
        assert len(results) == 0
