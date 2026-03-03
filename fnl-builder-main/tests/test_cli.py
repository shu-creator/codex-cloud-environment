"""Tests for CLI argument parsing and validation."""
from __future__ import annotations

import os
from importlib.metadata import version as pkg_version
from pathlib import Path
import subprocess
import sys

import pytest

from fnl_builder.cli import _parse_args, _validate_input_mode, main


class TestParseArgs:
    def test_individual_files(self) -> None:
        args = _parse_args([
            "--rl", "rl.pdf", "--pl", "pl.pdf",
            "--ml", "ml.pdf", "--template", "tpl.xlsx",
            "--out", "out.xlsx",
        ])
        assert str(args.roominglist_path) == "rl.pdf"
        assert str(args.passengerlist_path) == "pl.pdf"
        assert str(args.messagelist_path) == "ml.pdf"
        assert str(args.template_path) == "tpl.xlsx"
        assert str(args.out_path) == "out.xlsx"

    def test_zip_mode(self) -> None:
        args = _parse_args(["--zip", "bundle.zip", "--out", "out.xlsx"])
        assert str(args.zip_path) == "bundle.zip"

    def test_llm_provider_default(self) -> None:
        args = _parse_args(["--zip", "b.zip", "--out", "o.xlsx"])
        assert args.llm_provider == "none"

    def test_llm_provider_openai(self) -> None:
        args = _parse_args([
            "--zip", "b.zip", "--out", "o.xlsx", "--llm-provider", "openai",
        ])
        assert args.llm_provider == "openai"

    def test_audit_path(self) -> None:
        args = _parse_args([
            "--zip", "b.zip", "--out", "o.xlsx", "--audit", "audit.json",
        ])
        assert str(args.audit_path) == "audit.json"

    def test_audit_default_none(self) -> None:
        args = _parse_args(["--zip", "b.zip", "--out", "o.xlsx"])
        assert args.audit_path is None


class TestValidateInputMode:
    def test_zip_without_template_accepted(self) -> None:
        args = _parse_args(["--zip", "b.zip", "--out", "o.xlsx"])
        _validate_input_mode(args)  # no error — uses default template

    def test_individual_mode_valid(self) -> None:
        args = _parse_args([
            "--rl", "rl.pdf", "--pl", "pl.pdf",
            "--ml", "ml.pdf", "--template", "tpl.xlsx",
            "--out", "out.xlsx",
        ])
        _validate_input_mode(args)  # no error

    def test_zip_with_template_accepted(self) -> None:
        args = _parse_args([
            "--zip", "b.zip", "--template", "tpl.xlsx", "--out", "o.xlsx",
        ])
        _validate_input_mode(args)  # no error

    def test_zip_with_individual_rejected(self) -> None:
        args = _parse_args([
            "--zip", "b.zip", "--rl", "rl.pdf", "--out", "o.xlsx",
        ])
        with pytest.raises(SystemExit, match="mutually exclusive"):
            _validate_input_mode(args)

    def test_missing_some_individual(self) -> None:
        args = _parse_args(["--rl", "rl.pdf", "--out", "o.xlsx"])
        with pytest.raises(SystemExit, match="Missing required"):
            _validate_input_mode(args)

    def test_missing_all(self) -> None:
        args = _parse_args(["--out", "o.xlsx"])
        with pytest.raises(SystemExit, match="Either --zip or all"):
            _validate_input_mode(args)

    def test_missing_individual_lists_specific(self) -> None:
        args = _parse_args([
            "--rl", "rl.pdf", "--pl", "pl.pdf", "--out", "o.xlsx",
        ])
        with pytest.raises(SystemExit, match="--messagelist"):
            _validate_input_mode(args)

    def test_individual_without_template_accepted(self) -> None:
        args = _parse_args([
            "--rl", "rl.pdf", "--pl", "pl.pdf",
            "--ml", "ml.pdf", "--out", "out.xlsx",
        ])
        _validate_input_mode(args)  # no error — uses default template


def test_cli_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    expected_version = pkg_version("fnl-builder")
    assert f"fnl-builder {expected_version}" in captured.out


def test_cli_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--help"])
    assert exc_info.value.code == 0


def test_cli_usage_error_missing_out_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code == 2


def test_cli_usage_error_invalid_llm_provider_exits_two() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--zip", "b.zip", "--out", "o.xlsx", "--llm-provider", "invalid"])
    assert exc_info.value.code == 2


def test_cli_app_error_returns_one_in_subprocess() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        "src" if not existing_pythonpath else f"src{os.pathsep}{existing_pythonpath}"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "fnl_builder",
            "--roominglist",
            "rl.pdf",
            "--out",
            "out.xlsx",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert "Missing required individual file options" in proc.stderr
