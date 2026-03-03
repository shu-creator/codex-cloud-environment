from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from fnl_builder.shared.errors import FnlError
from fnl_builder.shared.io import atomic_save_workbook, atomic_write_text


def test_atomic_write_text_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    atomic_write_text(path, "hello")
    assert path.read_text(encoding="utf-8") == "hello"


def test_atomic_write_text_creates_parent_dirs(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "deep" / "out.txt"
    atomic_write_text(path, "nested")
    assert path.read_text(encoding="utf-8") == "nested"


def test_atomic_write_text_keeps_original_on_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "out.txt"
    path.write_text("original", encoding="utf-8")

    original_replace = Path.replace

    def fail_replace(self: Path, target: str | Path) -> Path:
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fail_replace)

    with pytest.raises(FnlError, match="ファイルの書き込みに失敗"):
        atomic_write_text(path, "updated")

    monkeypatch.setattr(Path, "replace", original_replace)
    assert path.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_save_workbook_creates_file(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"
    workbook = Workbook()
    atomic_save_workbook(path, workbook.save)
    assert path.exists()
    assert path.stat().st_size > 0


def test_atomic_save_workbook_no_partial_on_error(tmp_path: Path) -> None:
    path = tmp_path / "out.xlsx"

    def bad_save(save_path: str | Path) -> None:
        Path(save_path).write_bytes(b"partial")
        raise RuntimeError("save failed")

    with pytest.raises(RuntimeError, match="save failed"):
        atomic_save_workbook(path, bad_save)

    assert not path.exists()
    assert not list(tmp_path.glob("*.tmp.xlsx"))
