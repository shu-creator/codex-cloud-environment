from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import pytest

from fnl_builder.config import InputPaths, PipelineConfig, RunState
from fnl_builder.llm.adapter import NullAdapter
from fnl_builder.llm.mock import FullMockAdapter
from fnl_builder.shared.types import AuditLog, Issue, PipelineCounts


class TestPipelineConfig:
    def test_defaults(self) -> None:
        config = PipelineConfig(llm_provider="none")
        assert config.input_mode == "files"

    def test_is_frozen(self) -> None:
        config = PipelineConfig(llm_provider="none")
        with pytest.raises(FrozenInstanceError):
            setattr(config, "input_mode", "zip")


class TestInputPaths:
    def test_defaults(self) -> None:
        paths = InputPaths(rooming=Path("rooming.pdf"))
        assert paths.passenger is None
        assert paths.messagelist is None
        assert paths.template == Path()
        assert paths.output == Path()

    def test_is_frozen(self) -> None:
        paths = InputPaths(rooming=Path("rooming.pdf"))
        with pytest.raises(FrozenInstanceError):
            setattr(paths, "template", Path("template.xlsx"))


class TestRunStateFromConfig:
    @pytest.mark.parametrize(
        ("provider", "expected_adapter", "input_mode"),
        [
            ("none", NullAdapter, "files"),
            ("mock", FullMockAdapter, "zip"),
        ],
    )
    def test_provider_selection_and_audit_fields(
        self,
        provider: Literal["none", "mock"],
        expected_adapter: type[object],
        input_mode: Literal["files", "zip"],
    ) -> None:
        config = PipelineConfig(llm_provider=provider, input_mode=input_mode)
        state = RunState.from_config(config)

        assert isinstance(state.llm, expected_adapter)

        assert state.audit.started_at.endswith("Z")
        parsed = datetime.fromisoformat(state.audit.started_at.replace("Z", "+00:00"))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)

        assert state.audit.input_mode == config.input_mode
        assert state.issues == []

        assert isinstance(state.audit, AuditLog)
        assert isinstance(state.audit.counts, PipelineCounts)
        assert all(isinstance(issue, Issue) for issue in state.issues)
