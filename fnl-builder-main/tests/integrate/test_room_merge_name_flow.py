"""Tests for name-based room merge flow orchestration."""
from __future__ import annotations

from fnl_builder.integrate.room_merge_name_flow import resolve_name_based_room_merges
from fnl_builder.shared.types import Issue, NameResolution, NameRoomCandidate


def _mock_llm_resolver(
    candidates: list[NameRoomCandidate],
    llm_provider: str,
    known_output_inquiries: set[str],
) -> list[NameResolution]:
    """Mock LLM resolver that returns high-confidence results for all candidates."""
    results: list[NameResolution] = []
    for c in candidates:
        results.append({
            "candidate_id": c.candidate_id,
            "inquiry_a": "1234567890",
            "inquiry_b": "9876543210",
            "room_type": None,
            "confidence": 0.95,
        })
    return results


class TestResolveNameBasedRoomMerges:
    def test_no_candidates(self) -> None:
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text="普通のテキスト",
            known_output_inquiries=set(),
            llm_provider="none",
            issues=issues,
        )
        assert len(merges) == 0
        assert stats.candidates == 0

    def test_rule_only_resolution(self) -> None:
        text = (
            "1234567890-001\n"
            "#1234567890 TANAKA\n"
            "#9876543210 SUZUKI\n"
            "TANAKAとSUZUKI 同室"
        )
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="none",
            issues=issues,
        )
        assert len(merges) == 1
        assert merges[0].source == "rule_name"
        assert stats.rule_resolved == 1

    def test_llm_skipped_warning(self) -> None:
        text = "TANAKAとSUZUKI 同室"
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="none",
            issues=issues,
        )
        assert len(merges) == 0
        assert stats.unresolved == 1
        assert any(i.code == "room_merge_name_resolution_llm_skipped" for i in issues)

    def test_llm_resolution(self) -> None:
        text = "TANAKAとSUZUKI 同室"
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="openai",
            issues=issues,
            llm_resolver=_mock_llm_resolver,
        )
        assert len(merges) == 1
        assert merges[0].source == "llm_name"
        assert stats.llm_resolved == 1

    def test_llm_low_confidence_rejected(self) -> None:
        def low_conf_resolver(
            candidates: list[NameRoomCandidate],
            llm_provider: str,
            known: set[str],
        ) -> list[NameResolution]:
            return [{
                "candidate_id": candidates[0].candidate_id,
                "inquiry_a": "1234567890",
                "inquiry_b": "9876543210",
                "room_type": None,
                "confidence": 0.5,  # below 0.85 threshold
            }]

        text = "TANAKAとSUZUKI 同室"
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="openai",
            issues=issues,
            llm_resolver=low_conf_resolver,
        )
        assert len(merges) == 0
        assert stats.unresolved == 1

    def test_llm_unknown_inquiry_rejected(self) -> None:
        def bad_inq_resolver(
            candidates: list[NameRoomCandidate],
            llm_provider: str,
            known: set[str],
        ) -> list[NameResolution]:
            return [{
                "candidate_id": candidates[0].candidate_id,
                "inquiry_a": "1234567890",
                "inquiry_b": "0000000000",  # not in known
                "room_type": None,
                "confidence": 0.95,
            }]

        text = "TANAKAとSUZUKI 同室"
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="openai",
            issues=issues,
            llm_resolver=bad_inq_resolver,
        )
        assert len(merges) == 0

    def test_no_llm_resolver_unresolved(self) -> None:
        text = "TANAKAとSUZUKI 同室"
        issues: list[Issue] = []
        merges, stats = resolve_name_based_room_merges(
            text=text,
            known_output_inquiries={"1234567890", "9876543210"},
            llm_provider="openai",
            issues=issues,
            llm_resolver=None,
        )
        assert len(merges) == 0
        assert stats.unresolved == 1
        assert any(i.code == "room_merge_name_resolution_unresolved" for i in issues)
