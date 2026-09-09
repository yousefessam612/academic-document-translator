"""Document analyzer: extraction + scanned detection + OCR fallback + stats."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.core.logging_config import get_logger
from app.services.document import pdf_extractor, docx_extractor, txt_extractor
from app.services.document.structure import (
    Block,
    blocks_to_json,
    count_blocks,
    detect_title,
    HEADING,
)
from app.services.ocr import OCRManager, OCREngineNotAvailable

logger = get_logger(__name__)

# avg chars/page below which we consider a text layer "little or no text"
SCANNED_CHAR_THRESHOLD = 40


class AnalysisError(Exception):
    pass


class DocumentAnalyzer:
    def __init__(self, ocr_manager: OCRManager | None = None):
        self.ocr = ocr_manager or OCRManager()

    def analyze(
        self,
        path: Path,
        file_type: str,
        original_filename: str,
        status_cb: Callable[[str], None] | None = None,
        use_ocr_if_needed: bool = True,
    ) -> dict[str, Any]:
        """Analyze a document and return the full analysis + structure payload.

        Raises AnalysisError on fatal problems (e.g. scanned PDF and OCR unavailable).
        """

        def report(status: str) -> None:
            if status_cb:
                status_cb(status)

        ext = file_type.lower().lstrip(".")
        if ext == "pdf":
            blocks, analysis = self._analyze_pdf(path, report, use_ocr_if_needed)
        elif ext == "docx":
            report("extracting")
            try:
                blocks, stats = docx_extractor.extract_docx_blocks(path)
            except Exception as exc:
                raise AnalysisError(
                    f"Could not read the DOCX file. It may be corrupted. ({type(exc).__name__})"
                ) from exc
            analysis = self._build_analysis(ext, path, blocks, stats, ocr_used=False)
        elif ext == "txt":
            report("extracting")
            blocks, stats = txt_extractor.extract_txt_blocks(path)
            analysis = self._build_analysis(ext, path, blocks, stats, ocr_used=False)
        else:
            raise AnalysisError(f"Unsupported file type: {ext}")

        analysis["title"] = detect_title(blocks, original_filename)
        analysis["structure"] = blocks_to_json(blocks)
        return analysis

    # ------------------------------------------------------------------ PDF
    def _analyze_pdf(
        self, path: Path, report: Callable[[str], None], use_ocr_if_needed: bool
    ) -> tuple[list[Block], dict]:
        report("extracting")
        try:
            scanned, scan_info = pdf_extractor.is_scanned_pdf(path)
        except Exception as exc:
            raise AnalysisError(
                f"Could not open the PDF file. It may be corrupted. ({type(exc).__name__})"
            ) from exc

        ocr_used = False
        if not scanned:
            try:
                blocks, stats = pdf_extractor.extract_pdf_blocks(path)
            except Exception as exc:
                raise AnalysisError(
                    f"PDF text extraction failed. ({type(exc).__name__}: {exc})"
                ) from exc
            # Re-check: some PDFs pass the sample check but have no real text.
            pages = stats["page_count"] or 1
            if stats["character_count"] / pages < SCANNED_CHAR_THRESHOLD:
                scanned = True

        if scanned:
            report("ocr")
            if not use_ocr_if_needed:
                raise AnalysisError(
                    "The PDF appears to be scanned (no extractable text). Enable "
                    "'Use OCR' to translate scanned documents."
                )
            logger.info(
                "Scanned PDF detected, running OCR",
                extra={"operation": "analyze", "status": "ocr", "document_path": path.name},
            )
            try:
                pages = self.ocr.ocr_pdf(
                    path,
                    pdf_extractor.render_page_to_png,
                    progress_callback=lambda done, total: report(f"ocr {done}/{total}"),
                )
            except OCREngineNotAvailable:
                raise AnalysisError(
                    "The PDF appears to be scanned. OCR processing is required, but "
                    "Tesseract OCR is not installed on this machine. Install it from "
                    "https://github.com/UB-Mannheim/tesseract/wiki (or set TESSERACT_CMD "
                    "in .env) and analyze the document again."
                )
            except Exception as exc:
                raise AnalysisError(f"OCR processing failed: {type(exc).__name__}: {exc}") from exc

            blocks = self.ocr.pages_to_blocks(pages)
            total_chars = sum(len(b.text) for b in blocks)
            stats = {
                "page_count": len(pages),
                "character_count": total_chars,
                "paragraph_count": sum(1 for b in blocks if b.type == "paragraph"),
                "scan_info": scan_info,
            }
            ocr_used = True

        analysis = self._build_analysis("pdf", path, blocks, stats, ocr_used=ocr_used, scanned=scanned)
        return blocks, analysis

    # ------------------------------------------------------------- analysis
    def _build_analysis(
        self,
        file_type: str,
        path: Path,
        blocks: list[Block],
        stats: dict,
        ocr_used: bool,
        scanned: bool = False,
    ) -> dict[str, Any]:
        counts = count_blocks(blocks)
        # Translation units = paragraphs + list items + tables + headings (headings translate too)
        units = counts["paragraphs"] + counts["list_items"] + counts["tables"] + counts["headings"]

        # Dry-run chunk estimate via SmartChunker
        from app.services.translation.chunker import SmartChunker

        chunker = SmartChunker()
        chunks = chunker.chunk(blocks)
        chapters = []
        for b in blocks:
            if b.type == HEADING and b.level == 1 and b.text.strip():
                chapters.append(b.text.strip()[:200])
            if len(chapters) >= 50:
                break

        return {
            "file_type": file_type,
            "file_size": path.stat().st_size,
            "page_count": stats.get("page_count"),
            "has_extractable_text": stats.get("character_count", 0) > 0,
            "is_scanned": scanned or ocr_used,
            "ocr_used": ocr_used,
            "character_count": stats.get("character_count", sum(len(b.text) for b in blocks)),
            "heading_count": counts["headings"],
            "paragraph_count": counts["paragraphs"],
            "table_count": counts["tables"],
            "list_item_count": counts["list_items"],
            "estimated_translation_units": units,
            "estimated_chunks": len(chunks),
            "chapters": chapters,
        }
