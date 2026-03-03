"""E2E golden test for E417 1008 pipeline run.

Requires real PDF fixtures. Set ``FNL_E2E_FIXTURE_DIR`` to the directory
containing the three PDFs. Skipped automatically when the env var is unset.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from fnl_builder.config import InputPaths, PipelineConfig, RunState
from fnl_builder.pipeline import integrate_stage, parse_stage, render_stage

_FIXTURE_DIR = Path(os.environ["FNL_E2E_FIXTURE_DIR"]) if "FNL_E2E_FIXTURE_DIR" in os.environ else None
_FIXTURES = Path(__file__).parent / "fixtures" / "e417_1008"

_RL_PATH = (_FIXTURE_DIR / "ルーミングリスト_E417_20261008.pdf") if _FIXTURE_DIR else Path()
_PL_PATH = (_FIXTURE_DIR / "PSGリスト_E417_20261008.pdf") if _FIXTURE_DIR else Path()
_ML_PATH = (_FIXTURE_DIR / "MSGリスト_E417_20261008.pdf") if _FIXTURE_DIR else Path()
_TEMPLATE_PATH = _FIXTURES / "template.xlsx"
_EXPECTED_PATH = _FIXTURES / "expected.json"

_PDFS_AVAILABLE = _FIXTURE_DIR is not None and _RL_PATH.exists() and _PL_PATH.exists() and _ML_PATH.exists()

pytestmark = pytest.mark.skipif(not _PDFS_AVAILABLE, reason="Set FNL_E2E_FIXTURE_DIR to run E2E tests")


def _load_expected() -> dict[str, object]:
    return json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))  # type: ignore[return-value]


def _run_pipeline(tmp_path: Path) -> tuple[RunState, object]:
    config = PipelineConfig(
        llm_provider="none",
        input_paths=InputPaths(
            rooming=_RL_PATH,
            passenger=_PL_PATH,
            messagelist=_ML_PATH,
            template=_TEMPLATE_PATH,
            output=tmp_path / "out.xlsx",
        ),
    )
    state = RunState.from_config(config)
    parsed, ml_pages = parse_stage(state)
    integrated = integrate_stage(parsed, state, ml_pages=ml_pages)
    render_stage(integrated, state, rooming=parsed.rooming)
    return state, integrated


def test_e2e_guest_count(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    assert len(integrated.guests) == expected["guest_count"]


def test_e2e_guest_family_names(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    actual_names = [g.family_name for g in integrated.guests]
    expected_names = [g["family_name"] for g in expected["guests"]]
    assert actual_names == expected_names


def test_e2e_room_types(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    actual_types = [g.room_type for g in integrated.guests]
    expected_types = [g["room_type"] for g in expected["guests"]]
    assert actual_types == expected_types


def test_e2e_course_codes(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    actual_codes = [g.course_code for g in integrated.guests]
    expected_codes = [g["course_code"] for g in expected["guests"]]
    assert actual_codes == expected_codes


def test_e2e_remarks_counts(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    actual_counts = [len(g.remarks_parts) for g in integrated.guests]
    expected_counts = [g["remarks_count"] for g in expected["guests"]]
    assert actual_counts == expected_counts


def test_e2e_issue_codes(tmp_path: Path) -> None:
    expected = _load_expected()
    state, _ = _run_pipeline(tmp_path)
    actual_codes = sorted({i.code for i in state.issues})
    assert actual_codes == expected["issue_codes"]


def test_e2e_rewrite_stats(tmp_path: Path) -> None:
    expected = _load_expected()
    _, integrated = _run_pipeline(tmp_path)
    assert integrated.stats.candidates == expected["stats"]["candidates"]
    assert integrated.stats.fallback == expected["stats"]["fallback"]


def test_e2e_output_xlsx_exists(tmp_path: Path) -> None:
    _run_pipeline(tmp_path)
    assert (tmp_path / "out.xlsx").exists()
