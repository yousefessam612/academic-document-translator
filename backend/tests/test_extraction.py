"""Extraction tests: PDF text, DOCX structure, TXT, scanned-PDF detection, OCR."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.document import pdf_extractor, docx_extractor, txt_extractor
from app.services.document.analyzer import AnalysisError, DocumentAnalyzer
from app.services.ocr import OCRManager, OCREngineNotAvailable
from tests.conftest import make_docx, make_scanned_pdf, make_text_pdf


class TestPdfExtraction:
    def test_text_pdf_extraction(self, tmp_path: Path):
        pdf = make_text_pdf(tmp_path / "book.pdf", pages=3)
        blocks, stats = pdf_extractor.extract_pdf_blocks(pdf)
        assert stats["page_count"] == 3
        assert stats["character_count"] > 100
        types = {b.type for b in blocks}
        assert "heading" in types
        assert "paragraph" in types
        headings = [b for b in blocks if b.type == "heading"]
        assert any("Chapter 1" in h.text for h in headings)

    def test_scanned_detection(self, tmp_path: Path):
        text_pdf = make_text_pdf(tmp_path / "text.pdf")
        scanned_pdf = make_scanned_pdf(tmp_path / "scanned.pdf")
        assert pdf_extractor.is_scanned_pdf(text_pdf)[0] is False
        assert pdf_extractor.is_scanned_pdf(scanned_pdf)[0] is True

    def test_page_count(self, tmp_path: Path):
        pdf = make_text_pdf(tmp_path / "book.pdf", pages=5)
        assert pdf_extractor.page_count(pdf) == 5


class TestDocxExtraction:
    def test_structure_preserved(self, tmp_path: Path):
        docx = make_docx(tmp_path / "doc.docx")
        blocks, stats = docx_extractor.extract_docx_blocks(docx)
        types = [b.type for b in blocks]
        assert "heading" in types
        assert "paragraph" in types
        assert "list_item" in types
        assert "table" in types

        headings = [b for b in blocks if b.type == "heading"]
        assert headings[0].level == 1
        assert "Braille Literacy" in headings[0].text

        # Bold/italic markers preserved
        para = next(b for b in blocks if b.type == "paragraph" and "**" in b.text)
        assert "**Visual impairment**" in para.text
        assert "*learning outcomes*" in para.text

        table = next(b for b in blocks if b.type == "table")
        assert table.rows[0] == ["Term", "Arabic", "Domain"]
        assert table.rows[1][1] == "ضعف البصر"

    def test_list_detection(self, tmp_path: Path):
        docx = make_docx(tmp_path / "doc.docx")
        blocks, _ = docx_extractor.extract_docx_blocks(docx)
        items = [b for b in blocks if b.type == "list_item"]
        assert len(items) == 3
        assert any("Screen reader" in i.text for i in items)


class TestTxtExtraction:
    def test_paragraphs_and_headings(self, tmp_path: Path):
        path = tmp_path / "notes.txt"
        path.write_text(
            "Chapter 1 Overview\n\n"
            "First paragraph here.\n\n"
            "Second paragraph here.\n\n"
            "- item one\n- item two\n\n",
            encoding="utf-8",
        )
        blocks, stats = txt_extractor.extract_txt_blocks(path)
        types = [b.type for b in blocks]
        assert "heading" in types
        assert "paragraph" in types
        assert "list_item" in types
        assert stats["character_count"] > 20


class TestAnalyzer:
    def test_analyze_pdf(self, tmp_path: Path):
        pdf = make_text_pdf(tmp_path / "book.pdf")
        analyzer = DocumentAnalyzer()
        analysis = analyzer.analyze(pdf, "pdf", "book.pdf")
        assert analysis["file_type"] == "pdf"
        assert analysis["page_count"] == 3
        assert analysis["has_extractable_text"] is True
        assert analysis["is_scanned"] is False
        assert analysis["character_count"] > 100
        assert analysis["estimated_chunks"] >= 1
        assert analysis["estimated_translation_units"] >= 1
        assert len(analysis["structure"]) > 0

    def test_analyze_docx(self, tmp_path: Path):
        docx = make_docx(tmp_path / "doc.docx")
        analysis = DocumentAnalyzer().analyze(docx, "docx", "doc.docx")
        assert analysis["heading_count"] >= 2
        assert analysis["table_count"] == 1
        assert analysis["list_item_count"] == 3
        assert analysis["title"] == "Braille Literacy Study"

    def test_analyze_scanned_without_ocr_raises_clear_error(self, tmp_path: Path):
        scanned = make_scanned_pdf(tmp_path / "scanned.pdf")
        analyzer = DocumentAnalyzer()
        with pytest.raises(AnalysisError) as exc_info:
            analyzer.analyze(scanned, "pdf", "scanned.pdf", use_ocr_if_needed=False)
        assert "scanned" in str(exc_info.value).lower()

    def test_analyze_scanned_with_ocr_when_available(self, tmp_path: Path):
        scanned = make_scanned_pdf(tmp_path / "scanned.pdf")
        manager = OCRManager()
        if not manager.engine_status()[0]["available"]:
            pytest.skip("Tesseract OCR is not installed on this machine")
        analysis = DocumentAnalyzer(manager).analyze(scanned, "pdf", "scanned.pdf")
        assert analysis["ocr_used"] is True
        assert analysis["is_scanned"] is True
        assert analysis["character_count"] > 10


class TestOCRAvailability:
    def test_engine_status_reports(self):
        status = OCRManager().engine_status()
        assert isinstance(status, list)
        assert all("name" in s and "available" in s for s in status)
