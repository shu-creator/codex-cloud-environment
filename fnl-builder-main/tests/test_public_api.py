"""Smoke tests for the public API surface."""
from __future__ import annotations


def test_public_api_importable() -> None:
    from fnl_builder import (
        AuditLog,
        FnlError,
        GuestRecord,
        InputError,
        InputPaths,
        IntegrationResult,
        LLMError,
        ParseError,
        ParseResult,
        PipelineConfig,
        RenderResult,
        run,
    )

    assert callable(run)
    # Verify key types are accessible
    for cls in (
        AuditLog, GuestRecord, InputPaths, PipelineConfig,
        IntegrationResult, ParseResult, RenderResult,
    ):
        assert isinstance(cls, type)
    # Verify error hierarchy
    assert issubclass(InputError, FnlError)
    assert issubclass(ParseError, FnlError)
    assert issubclass(LLMError, FnlError)
