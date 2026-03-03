"""Tests for ZIP archive extraction and file identification."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from fnl_builder.parse.zip_extract import extract_zip
from fnl_builder.shared.errors import InputError


def _create_zip(zip_path: Path, filenames: list[str]) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in filenames:
            zf.writestr(name, f"dummy content for {name}")


def test_extract_zip_identifies_all_three(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, [
        "ルーミングリスト_E417_20261008.pdf",
        "PSGリスト_E417_20261008.pdf",
        "MSGリスト_E417_20261008.pdf",
    ])
    dest = tmp_path / "out"
    dest.mkdir()
    paths = extract_zip(zip_path, dest)

    assert paths.rooming.name == "ルーミングリスト_E417_20261008.pdf"
    assert paths.passenger is not None
    assert paths.passenger.name == "PSGリスト_E417_20261008.pdf"
    assert paths.messagelist is not None
    assert paths.messagelist.name == "MSGリスト_E417_20261008.pdf"


def test_extract_zip_missing_rooming_raises(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, ["PSGリスト_E417.pdf", "MSGリスト_E417.pdf"])
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(InputError, match="ルーミングリスト"):
        extract_zip(zip_path, dest)


def test_extract_zip_rooming_only(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, ["ルーミングリスト_E417.pdf"])
    dest = tmp_path / "out"
    dest.mkdir()
    paths = extract_zip(zip_path, dest)

    assert paths.rooming.name == "ルーミングリスト_E417.pdf"
    assert paths.passenger is None
    assert paths.messagelist is None


def test_extract_zip_english_filenames(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, ["rooming.pdf", "passenger.pdf", "messagelist.csv"])
    dest = tmp_path / "out"
    dest.mkdir()
    paths = extract_zip(zip_path, dest)

    assert paths.rooming.name == "rooming.pdf"
    assert paths.passenger is not None
    assert paths.passenger.name == "passenger.pdf"
    assert paths.messagelist is not None
    assert paths.messagelist.name == "messagelist.csv"


def test_extract_zip_ignores_non_pdf_csv(tmp_path: Path) -> None:
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, [
        "ルーミングリスト.pdf",
        "ルーミングリスト.xlsx",
        "readme.txt",
    ])
    dest = tmp_path / "out"
    dest.mkdir()
    paths = extract_zip(zip_path, dest)

    assert paths.rooming.name == "ルーミングリスト.pdf"
    assert paths.passenger is None
    assert paths.messagelist is None


def test_extract_zip_csv_rooming_not_matched(tmp_path: Path) -> None:
    """CSV files should not match rooming or passenger (PDF-only)."""
    zip_path = tmp_path / "bundle.zip"
    _create_zip(zip_path, ["rooming.csv", "passenger.csv", "ルーミングリスト.pdf"])
    dest = tmp_path / "out"
    dest.mkdir()
    paths = extract_zip(zip_path, dest)

    assert paths.rooming.name == "ルーミングリスト.pdf"
    assert paths.passenger is None


def test_extract_zip_path_traversal_rejected(tmp_path: Path) -> None:
    """ZIP entries with path traversal should be rejected."""
    zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../etc/passwd", "evil")
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(InputError, match="展開先の外"):
        extract_zip(zip_path, dest)


def test_extract_zip_bad_zip_raises_input_error(tmp_path: Path) -> None:
    """Corrupt or non-ZIP files should raise InputError, not BadZipFile."""
    bad_file = tmp_path / "not_a.zip"
    bad_file.write_text("this is not a zip file")
    dest = tmp_path / "out"
    dest.mkdir()

    with pytest.raises(InputError, match="ZIP形式ではありません"):
        extract_zip(bad_file, dest)
