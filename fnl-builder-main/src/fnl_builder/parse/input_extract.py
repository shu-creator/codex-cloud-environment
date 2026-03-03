from __future__ import annotations

import csv
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast
from collections.abc import Callable

from fnl_builder.shared.text import collapse_ws

_logger = logging.getLogger(__name__)

# CSV encoding detection order (UTF-8 first to avoid misreading as CP932)
_CSV_ENCODINGS = ["utf-8", "utf-8-sig", "cp932", "shift_jis"]
_UTF8_BOM = b"\xef\xbb\xbf"

# MessageList CSV column names
_ML_CSV_COL_INQUIRY_NO = "問合せNO"
_ML_CSV_COL_NO = "NO"
_ML_CSV_COL_CATEGORY = "確認手配事項"  # Contains registration type like "ランドオンリー"
_ML_CSV_COL_CONTENT = "確認手配事項内容"
_ML_CSV_COL_MEMO = "後方メモ"

_PAGE_MARKER_RE = re.compile(r"\[page\s+(\d+)\]")


@dataclass(frozen=True)
class PdfExtractionMeta:
    method: str  # 'pdftotext' or 'pypdf'
    total_pages: int = 0
    failed_pages: list[int] = field(default_factory=list)
    returncode: int | None = None
    stderr_len: int | None = None


@dataclass(frozen=True)
class CsvExtractionMeta:
    method: str  # always 'csv'
    encoding: str = "utf-8"
    total_rows: int = 0
    failed_rows: list[int] = field(default_factory=list)
    error: str | None = None


ExtractionMeta = PdfExtractionMeta | CsvExtractionMeta


@dataclass(frozen=True)
class MessageListCsvRow:
    inquiry_no: str
    no: str
    category: str
    content: str
    memo: str


class _PdfPage(Protocol):
    def extract_text(self) -> str | None: ...


class _PdfReader(Protocol):
    pages: list[_PdfPage]


def _load_pdf_reader() -> Callable[[str], _PdfReader]:
    module = __import__("pypdf", fromlist=["PdfReader"])
    reader = getattr(module, "PdfReader")
    return cast(Callable[[str], _PdfReader], reader)


def _extract_pdf_pages_pypdf(pdf_path: Path) -> tuple[list[tuple[int, str]], int, list[int]]:
    reader_cls = _load_pdf_reader()
    reader = reader_cls(str(pdf_path))
    pages: list[tuple[int, str]] = []
    failed: list[int] = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            pages.append((idx, text))
        except Exception as exc:
            _logger.debug("PDF page %d extraction failed: %s", idx, exc)
            failed.append(idx)
    return pages, len(reader.pages), failed


def extract_pdf_text(pdf_path: Path) -> tuple[str, PdfExtractionMeta]:
    """Best-effort PDF -> text with provenance info for audit."""
    # On some macOS/Python combinations, subprocess fork from multi-threaded apps can crash.
    can_run_pdftotext = bool(shutil.which("pdftotext"))
    if os.getenv("FNL_DISABLE_PDFTOTEXT_SUBPROCESS", "").strip() == "1":
        can_run_pdftotext = False
    if sys.platform == "darwin" and threading.active_count() > 1:
        can_run_pdftotext = False

    if can_run_pdftotext:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_txt = Path(tmpdir) / "out.txt"
            cmd = ["pdftotext", "-layout", str(pdf_path), str(out_txt)]
            # Avoid check=True so failures don't raise with stderr/stdout content; fallback to pypdf instead.
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0 and out_txt.exists():
                text = out_txt.read_text(errors="ignore")
                return text, PdfExtractionMeta(
                    method="pdftotext",
                    returncode=proc.returncode,
                    stderr_len=len(proc.stderr or ""),
                )

    pages, total_pages, failed_pages = _extract_pdf_pages_pypdf(pdf_path)
    combined = "\n\n".join(f"[page {page_no}]\n{text}" for page_no, text in pages)
    return combined, PdfExtractionMeta(
        method="pypdf",
        total_pages=total_pages,
        failed_pages=failed_pages,
    )


def detect_csv_encoding(csv_path: Path) -> str:
    """Detect CSV file encoding by trying multiple encodings.

    Priority: UTF-8 BOM -> UTF-8 -> UTF-8-SIG -> CP932 -> Shift-JIS
    """
    raw_bytes = csv_path.read_bytes()

    if raw_bytes.startswith(_UTF8_BOM):
        return "utf-8-sig"

    for encoding in _CSV_ENCODINGS:
        try:
            raw_bytes.decode(encoding)
            return encoding
        except (UnicodeDecodeError, LookupError):
            continue

    return "cp932"


def build_csv_who_id(inquiry_no: str, no: str) -> str:
    """Build who_id in 10-digit-3-digit format for assign_who_fields compatibility."""
    if not inquiry_no or not inquiry_no.isdigit():
        return ""

    padded_inquiry = inquiry_no.zfill(10)
    try:
        branch = int(no) if no and no.isdigit() else 1
        return f"{padded_inquiry}-{branch:03d}"
    except ValueError:
        return f"{padded_inquiry}-001"


def build_csv_row_parts(
    *,
    inquiry_no: str,
    no: str,
    category: str,
    content: str,
    memo: str,
) -> list[str]:
    parts: list[str] = []

    who_id = build_csv_who_id(inquiry_no, no)
    if who_id:
        parts.append(f"顧客 {who_id}")

    if content:
        if inquiry_no:
            if category:
                parts.append(f"[問合せNO: {inquiry_no}] [{category}] {content}")
            else:
                parts.append(f"[問合せNO: {inquiry_no}] {content}")
        elif category:
            parts.append(f"[{category}] {content}")
        else:
            parts.append(content)
    elif category:
        if inquiry_no:
            parts.append(f"[問合せNO: {inquiry_no}] [{category}]")
        else:
            parts.append(f"[{category}]")
    elif inquiry_no:
        parts.append(f"[問合せNO: {inquiry_no}]")

    if memo:
        parts.append(f"[後方メモ] {memo}")

    return parts


def extract_csv_text(csv_path: Path) -> tuple[str, CsvExtractionMeta]:
    """Extract text from MessageList CSV with provenance info for audit."""
    rows, meta = extract_csv_rows(csv_path)
    text_parts: list[str] = []
    for row in rows:
        parts = build_csv_row_parts(
            inquiry_no=row.inquiry_no,
            no=row.no,
            category=row.category,
            content=row.content,
            memo=row.memo,
        )
        if parts:
            text_parts.append("\n".join(parts))

    combined = "\n\n".join(text_parts)
    return combined, meta


def build_csv_llm_text(rows: list[MessageListCsvRow]) -> str:
    text_parts = ["\n".join(parts) for row in rows if (parts := _build_csv_row_parts_for_llm(row))]
    return "\n\n".join(text_parts)


def _build_csv_row_parts_for_llm(row: MessageListCsvRow) -> list[str]:
    parts: list[str] = []
    who_id = build_csv_who_id(row.inquiry_no, row.no)
    if who_id:
        parts.append(f"顧客 {who_id}")
    combined_body = collapse_ws(" ".join(part for part in [row.content, row.memo] if part))
    formatted = _format_csv_body_with_headers(
        inquiry_no=row.inquiry_no,
        category=row.category,
        combined_body=combined_body,
    )
    if formatted:
        parts.append(formatted)
    return parts


def _format_csv_body_with_headers(
    *,
    inquiry_no: str,
    category: str,
    combined_body: str,
) -> str:
    if inquiry_no:
        prefix = f"[問合せNO: {inquiry_no}]"
        if category:
            return f"{prefix} [{category}] {combined_body}".strip()
        if combined_body:
            return f"{prefix} {combined_body}".strip()
        return prefix
    if category:
        return f"[{category}] {combined_body}".strip()
    return combined_body


def extract_csv_rows(csv_path: Path) -> tuple[list[MessageListCsvRow], CsvExtractionMeta]:
    """Extract structured rows from MessageList CSV."""
    rows: list[MessageListCsvRow] = []
    total_rows = 0
    failed_rows: list[int] = []
    encoding = "utf-8"

    try:
        encoding = detect_csv_encoding(csv_path)
        with csv_path.open("r", encoding=encoding, newline="") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader, start=1):
                total_rows += 1
                try:
                    rows.append(
                        MessageListCsvRow(
                            inquiry_no=(row.get(_ML_CSV_COL_INQUIRY_NO, "") or "").strip(),
                            no=(row.get(_ML_CSV_COL_NO, "") or "").strip(),
                            category=(row.get(_ML_CSV_COL_CATEGORY, "") or "").strip(),
                            content=(row.get(_ML_CSV_COL_CONTENT, "") or "").strip(),
                            memo=(row.get(_ML_CSV_COL_MEMO, "") or "").strip(),
                        )
                    )
                except Exception:
                    failed_rows.append(row_idx)
    except Exception as exc:
        return [], CsvExtractionMeta(
            method="csv",
            encoding=encoding,
            error=type(exc).__name__,
            total_rows=0,
            failed_rows=[],
        )

    return rows, CsvExtractionMeta(
        method="csv",
        encoding=encoding,
        total_rows=total_rows,
        failed_rows=failed_rows,
    )


def _extract_messagelist_pdf_text(pdf_path: Path) -> tuple[str, PdfExtractionMeta]:
    """Extract MessageList PDF text with page markers.

    Always uses pypdf for page-level extraction so that ``text_to_pages``
    can split the text back into per-page chunks. ``pdftotext -layout``
    merges multiple logical pages and drops page boundaries, which breaks
    page-based who_id inference and p_marker processing.
    """
    pages, total_pages, failed_pages = _extract_pdf_pages_pypdf(pdf_path)
    combined = "\n\n".join(f"[page {page_no}]\n{text}" for page_no, text in pages)
    return combined, PdfExtractionMeta(
        method="pypdf",
        total_pages=total_pages,
        failed_pages=failed_pages,
    )


def extract_messagelist_text(path: Path, *, is_csv: bool) -> tuple[str, ExtractionMeta]:
    if is_csv:
        return extract_csv_text(path)
    return _extract_messagelist_pdf_text(path)


def text_to_pages(text: str) -> list[tuple[int, str]]:
    """Convert extracted text to adapter page tuples."""
    matches = list(_PAGE_MARKER_RE.finditer(text))
    if matches:
        pages: list[tuple[int, str]] = []
        for index, match in enumerate(matches):
            page_no = int(match.group(1))
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            page_text = text[start:end].strip()
            if page_text:
                pages.append((page_no, page_text))
        return pages
    return [(1, text.strip())] if text.strip() else []
