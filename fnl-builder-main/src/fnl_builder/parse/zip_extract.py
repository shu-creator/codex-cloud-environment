"""Extract and identify FNL documents from a ZIP archive."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

from fnl_builder.config import InputPaths
from fnl_builder.shared.errors import InputError

_ROOMING_RE = re.compile(r"ルーミングリスト|rooming", re.IGNORECASE)
_PASSENGER_RE = re.compile(r"PSGリスト|パッセンジャー|passenger", re.IGNORECASE)
_MESSAGELIST_RE = re.compile(r"MSGリスト|メッセージリスト|messagelist", re.IGNORECASE)
_PDF_ONLY = frozenset({".pdf"})
_PDF_AND_CSV = frozenset({".pdf", ".csv"})


def extract_zip(zip_path: Path, dest: Path) -> InputPaths:
    """Extract a ZIP archive and identify FNL documents by filename patterns.

    Returns an InputPaths with rooming, passenger, and messagelist populated.
    template/output/audit are left as defaults (caller should override).
    """
    resolved_dest = dest.resolve()
    try:
        zf_ctx = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        raise InputError(f"ZIPファイルが破損しているか、ZIP形式ではありません: {zip_path.name}") from exc
    with zf_ctx as zf:
        for member in zf.namelist():
            target = (resolved_dest / member).resolve()
            if not target.is_relative_to(resolved_dest):
                raise InputError(f"ZIPエントリが展開先の外を参照しています: {member}")
        zf.extractall(dest)

    rooming: Path | None = None
    passenger: Path | None = None
    messagelist: Path | None = None

    for path in sorted(dest.rglob("*")):
        if path.is_dir():
            continue
        ext = path.suffix.lower()
        name = path.name
        if rooming is None and ext in _PDF_ONLY and _ROOMING_RE.search(name):
            rooming = path
        elif passenger is None and ext in _PDF_ONLY and _PASSENGER_RE.search(name):
            passenger = path
        elif messagelist is None and ext in _PDF_AND_CSV and _MESSAGELIST_RE.search(name):
            messagelist = path

    if rooming is None:
        raise InputError(
            "ZIP内にルーミングリストが見つかりません。"
            "ファイル名に「ルーミングリスト」または「rooming」を含めてください。"
        )

    return InputPaths(
        rooming=rooming,
        passenger=passenger,
        messagelist=messagelist,
    )
