from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from backend.app.config import Settings
from backend.app.services import documents


class FakePage:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_text(self, _mode: str) -> str:
        return self.text


class FakeDocument:
    def __init__(self, pages: list[str]) -> None:
        self.pages = [FakePage(text) for text in pages]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def __getitem__(self, index: int) -> FakePage:
        return self.pages[index]

    def __enter__(self) -> FakeDocument:
        return self

    def __exit__(self, *_args) -> None:
        return None


def test_text_file_uses_native_extraction(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Search trees\nBinary search trees preserve ordering.", encoding="utf-8")

    result = documents.extract_pages(path, "md")

    assert result.native_page_count == 1
    assert result.ocr_page_count == 0
    assert result.pages[0].source == "native"
    assert "Binary search trees" in result.pages[0].text


def test_pdf_only_sends_weak_pages_to_ocr(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        documents.fitz,
        "open",
        lambda _path: FakeDocument([
            "A complete native text layer with enough searchable characters for the OCR quality threshold. "
            "This extra sentence keeps the first page above the configured minimum.",
            "",
        ]),
    )
    calls: list[tuple[list[int], str, int]] = []

    def fake_ocr(_path: Path, page_numbers: list[int], *, language: str, dpi: int) -> dict[int, str]:
        calls.append((page_numbers, language, dpi))
        return {2: "OCR recovered the second page about binary search trees."}

    settings = Settings(pdf_ocr_language="chi_sim+eng", pdf_ocr_dpi=240)
    result = documents.extract_pages(tmp_path / "scan.pdf", "pdf", settings, fake_ocr)

    assert calls == [([2], "chi_sim+eng", 240)]
    assert result.native_page_count == 1
    assert result.ocr_page_count == 1
    assert [page.source for page in result.pages] == ["native", "ocr"]
    assert "binary search trees" in result.pages[1].text


def test_pdf_ocr_can_be_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(documents.fitz, "open", lambda _path: FakeDocument([""]))

    def unexpected_ocr(*_args, **_kwargs):
        raise AssertionError("OCR should not run when disabled")

    settings = Settings(pdf_ocr_enabled=False)
    result = documents.extract_pages(tmp_path / "scan.pdf", "pdf", settings, unexpected_ocr)

    assert result.native_page_count == 1
    assert result.ocr_page_count == 0
    assert result.pages[0].text == ""


def test_damaged_pdf_bubbles_a_safe_parser_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(documents.fitz, "open", lambda _path: (_ for _ in ()).throw(fitz.FileDataError("bad pdf")))

    with pytest.raises(fitz.FileDataError, match="bad pdf"):
        documents.extract_pages(tmp_path / "damaged.pdf", "pdf", Settings())


def test_ocr_language_falls_back_to_an_installed_requested_language(monkeypatch) -> None:
    monkeypatch.setattr(documents, "_tesseract_languages", lambda _command: {"eng", "osd"})

    assert documents._resolve_ocr_language("tesseract", "chi_sim+eng") == "eng"


def test_ocr_language_reports_missing_requested_languages(monkeypatch) -> None:
    monkeypatch.setattr(documents, "_tesseract_languages", lambda _command: {"osd"})

    with pytest.raises(RuntimeError, match="PDF_OCR_LANGUAGE_UNAVAILABLE"):
        documents._resolve_ocr_language("tesseract", "chi_sim+eng")
