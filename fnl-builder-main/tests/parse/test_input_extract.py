from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from fnl_builder.parse.input_extract import (
    CsvExtractionMeta,
    MessageListCsvRow,
    PdfExtractionMeta,
    _extract_pdf_pages_pypdf,
    build_csv_llm_text,
    build_csv_row_parts,
    build_csv_who_id,
    detect_csv_encoding,
    extract_csv_rows,
    extract_pdf_text,
    text_to_pages,
)


def test_text_to_pages_single() -> None:
    text = "one page text"
    assert text_to_pages(text) == [(1, "one page text")]


def test_text_to_pages_multiple() -> None:
    text = "[page 1]\nalpha\n\n[page 2]\nbeta"
    assert text_to_pages(text) == [(1, "alpha"), (2, "beta")]


def test_text_to_pages_empty() -> None:
    assert text_to_pages("") == []


def test_build_csv_who_id_normal() -> None:
    assert build_csv_who_id("67368202", "1") == "0067368202-001"


def test_build_csv_who_id_empty() -> None:
    assert build_csv_who_id("", "") == ""


def test_build_csv_who_id_non_digit() -> None:
    assert build_csv_who_id("abc", "1") == ""


def test_detect_csv_encoding_utf8(tmp_path: Path) -> None:
    csv_path = tmp_path / "m.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    assert detect_csv_encoding(csv_path) == "utf-8"


def test_detect_csv_encoding_bom(tmp_path: Path) -> None:
    csv_path = tmp_path / "m_bom.csv"
    csv_path.write_bytes(b"\xef\xbb\xbfa,b\n1,2\n")
    assert detect_csv_encoding(csv_path) == "utf-8-sig"


def test_build_csv_row_parts_full() -> None:
    parts = build_csv_row_parts(
        inquiry_no="67368202",
        no="1",
        category="ランドオンリー",
        content="内容",
        memo="備考",
    )
    assert parts == [
        "顧客 0067368202-001",
        "[問合せNO: 67368202] [ランドオンリー] 内容",
        "[後方メモ] 備考",
    ]


def test_build_csv_row_parts_content_only() -> None:
    parts = build_csv_row_parts(
        inquiry_no="",
        no="",
        category="",
        content="内容のみ",
        memo="",
    )
    assert parts == ["内容のみ"]


def test_extract_csv_rows_basic(tmp_path: Path) -> None:
    csv_path = tmp_path / "messagelist.csv"
    csv_path.write_text(
        "問合せNO,NO,確認手配事項,確認手配事項内容,後方メモ\n"
        "67368202,1,ランドオンリー,内容A,備考A\n",
        encoding="utf-8",
    )
    rows, meta = extract_csv_rows(csv_path)

    assert len(rows) == 1
    assert rows[0] == MessageListCsvRow(
        inquiry_no="67368202",
        no="1",
        category="ランドオンリー",
        content="内容A",
        memo="備考A",
    )
    assert meta.total_rows == 1
    assert meta.failed_rows == []
    assert meta.method == "csv"


def test_csv_extraction_meta_type(tmp_path: Path) -> None:
    csv_path = tmp_path / "messagelist.csv"
    csv_path.write_text("問合せNO,NO,確認手配事項,確認手配事項内容,後方メモ\n", encoding="utf-8")
    _rows, meta = extract_csv_rows(csv_path)
    assert isinstance(meta, CsvExtractionMeta)


@pytest.mark.skip(reason="No PDF fixture available for extraction test.")
def test_pdf_extraction_meta_type() -> None:
    # Intentionally skipped by default in this repository.
    assert isinstance(PdfExtractionMeta(method="pypdf"), PdfExtractionMeta)


def test_build_csv_llm_text() -> None:
    rows = [
        MessageListCsvRow(
            inquiry_no="67368202",
            no="1",
            category="ランドオンリー",
            content="内容",
            memo="メモ",
        ),
        MessageListCsvRow(
            inquiry_no="",
            no="",
            category="",
            content="単独行",
            memo="",
        ),
    ]
    assert (
        build_csv_llm_text(rows)
        == "顧客 0067368202-001\n[問合せNO: 67368202] [ランドオンリー] 内容 メモ\n\n単独行"
    )


class _StubPdfPage:
    def __init__(self, text: str | None = "", *, error: Exception | None = None) -> None:
        self._text = text
        self._error = error

    def extract_text(self) -> str | None:
        if self._error is not None:
            raise self._error
        return self._text


class _StubPdfReader:
    def __init__(self, pages: list[_StubPdfPage]) -> None:
        self.pages = pages


def test_extract_pdf_pages_pypdf_normal() -> None:
    reader = _StubPdfReader([_StubPdfPage("page1 text"), _StubPdfPage("page2 text")])

    def reader_factory(_path: str) -> _StubPdfReader:
        return reader

    with patch("fnl_builder.parse.input_extract._load_pdf_reader", return_value=reader_factory):
        pages, total_pages, failed_pages = _extract_pdf_pages_pypdf(Path("dummy.pdf"))

    assert pages == [(1, "page1 text"), (2, "page2 text")]
    assert total_pages == 2
    assert failed_pages == []


def test_extract_pdf_pages_pypdf_page_failure() -> None:
    reader = _StubPdfReader(
        [
            _StubPdfPage("ok page"),
            _StubPdfPage(error=RuntimeError("boom")),
        ]
    )

    def reader_factory(_path: str) -> _StubPdfReader:
        return reader

    with patch("fnl_builder.parse.input_extract._load_pdf_reader", return_value=reader_factory):
        pages, total_pages, failed_pages = _extract_pdf_pages_pypdf(Path("dummy.pdf"))

    assert pages == [(1, "ok page")]
    assert total_pages == 2
    assert failed_pages == [2]


def test_extract_pdf_pages_pypdf_empty_pdf() -> None:
    reader = _StubPdfReader([])

    def reader_factory(_path: str) -> _StubPdfReader:
        return reader

    with patch("fnl_builder.parse.input_extract._load_pdf_reader", return_value=reader_factory):
        pages, total_pages, failed_pages = _extract_pdf_pages_pypdf(Path("dummy.pdf"))

    assert pages == []
    assert total_pages == 0
    assert failed_pages == []


def test_extract_pdf_text_pdftotext_success(tmp_path: Path) -> None:
    pdf_path = tmp_path / "input.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    def run_success(cmd: list[str], **_kwargs: object) -> MagicMock:
        out_txt = Path(cmd[3])
        out_txt.write_text("pdftotext output", encoding="utf-8")
        proc: MagicMock = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        return proc

    with (
        patch("fnl_builder.parse.input_extract.shutil.which", return_value="pdftotext"),
        patch("fnl_builder.parse.input_extract.os.getenv", return_value=""),
        patch("fnl_builder.parse.input_extract.sys.platform", "linux"),
        patch("fnl_builder.parse.input_extract.threading.active_count", return_value=1),
        patch("fnl_builder.parse.input_extract.subprocess.run", side_effect=run_success),
    ):
        text, meta = extract_pdf_text(pdf_path)

    assert text == "pdftotext output"
    assert meta.method == "pdftotext"


def test_extract_pdf_text_pdftotext_fallback_to_pypdf() -> None:
    proc: MagicMock = MagicMock()
    proc.returncode = 1
    proc.stderr = "error"

    with (
        patch("fnl_builder.parse.input_extract.shutil.which", return_value="pdftotext"),
        patch("fnl_builder.parse.input_extract.os.getenv", return_value=""),
        patch("fnl_builder.parse.input_extract.sys.platform", "linux"),
        patch("fnl_builder.parse.input_extract.threading.active_count", return_value=1),
        patch("fnl_builder.parse.input_extract.subprocess.run", return_value=proc),
        patch(
            "fnl_builder.parse.input_extract._extract_pdf_pages_pypdf",
            return_value=([(1, "page1 text")], 1, []),
        ) as pypdf_extract,
    ):
        text, meta = extract_pdf_text(Path("dummy.pdf"))

    assert text == "[page 1]\npage1 text"
    assert meta.method == "pypdf"
    pypdf_extract.assert_called_once_with(Path("dummy.pdf"))


def test_extract_pdf_text_respects_disable_pdftotext_env_var() -> None:
    with (
        patch("fnl_builder.parse.input_extract.shutil.which", return_value="pdftotext"),
        patch("fnl_builder.parse.input_extract.os.getenv", return_value="1"),
        patch("fnl_builder.parse.input_extract.subprocess.run") as run_mock,
        patch(
            "fnl_builder.parse.input_extract._extract_pdf_pages_pypdf",
            return_value=([(1, "page1 text")], 1, []),
        ),
    ):
        text, meta = extract_pdf_text(Path("dummy.pdf"))

    assert text == "[page 1]\npage1 text"
    assert meta.method == "pypdf"
    run_mock.assert_not_called()
