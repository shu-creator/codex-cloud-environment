from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fnl_builder.llm.adapter import LLMAdapter, NullAdapter
from fnl_builder.shared.types import AuditLog, Issue, PipelineCounts


@dataclass(frozen=True)
class InputPaths:
    """Input/output file paths for the pipeline.

    ``rooming`` is required at the type level; ``passenger`` and ``messagelist``
    are optional to support Python API callers and ZIP extraction results.
    The CLI files-mode contract is stricter and validates all three input
    documents in ``fnl_builder.cli._validate_input_mode``.
    """

    rooming: Path
    passenger: Path | None = None
    messagelist: Path | None = None
    template: Path = Path()
    output: Path = Path()
    audit: Path | None = None


@dataclass(frozen=True)
class PipelineConfig:
    """Top-level pipeline configuration.

    ``llm_provider`` selects the LLM backend: ``"none"`` skips LLM extraction,
    ``"openai"`` uses the OpenAI API, ``"mock"`` uses a deterministic mock.
    """

    llm_provider: Literal["none", "openai", "mock"]
    input_mode: Literal["zip", "files"] = "files"
    input_paths: InputPaths = field(default_factory=lambda: InputPaths(rooming=Path()))


@dataclass
class RunState:
    config: PipelineConfig
    llm: LLMAdapter
    issues: list[Issue]
    audit: AuditLog

    @classmethod
    def from_config(cls, config: PipelineConfig) -> RunState:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        llm: LLMAdapter
        if config.llm_provider == "openai":
            from fnl_builder.llm.openai import OpenAIAdapter
            llm = OpenAIAdapter()
        elif config.llm_provider == "mock":
            from fnl_builder.llm.mock import FullMockAdapter
            llm = FullMockAdapter()
        else:
            llm = NullAdapter()
        return cls(
            config=config,
            llm=llm,
            issues=[],
            audit=AuditLog(
                started_at=started_at,
                input_mode=config.input_mode,
                input_files_sha256={},
                counts=PipelineCounts(),
            ),
        )
