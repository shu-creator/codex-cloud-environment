"""Atomic file write utilities."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from fnl_builder.shared.errors import FnlError


def _default_file_mode() -> int:
    """Return default file mode based on current umask (typically 0o644)."""
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text atomically via tmpfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            os.fchmod(fd, _default_file_mode())
            with open(fd, "w", encoding=encoding) as file:
                file.write(content)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise FnlError(f"ファイルの書き込みに失敗: {path}: {exc}") from exc


def atomic_save_workbook(path: Path, save_fn: Callable[[str | Path], None]) -> None:
    """Save openpyxl workbook atomically via tmpfile + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp.xlsx")
        os.fchmod(fd, _default_file_mode())
        os.close(fd)
        try:
            save_fn(tmp)
            Path(tmp).replace(path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise FnlError(f"出力ファイルの書き込みに失敗: {path}: {exc}") from exc
