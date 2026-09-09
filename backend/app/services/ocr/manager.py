"""OCR manager: picks the first available engine, exposes modular pipeline."""
from __future__ import annotations

import re
from pathlib import Path

from app.core.logging_config import get_logger
from app.services.ocr.base import OCREngine, OCREngineNotAvailable
from app.services.ocr.tesseract_engine import TesseractEngine

logger = get_logger(__name__)

_CHAPTER_RE = re.compile(r"^\s*(chapter|part)\s+[\dIVXLC]+", re.IGNORECASE)


class OCRManager:
    def __init__(self) -> None:
        self._engines: list[OCREngine] = [TesseractEngine()]

    def engine_status(self) -> list[dict]:
        return [
            {"name": e.name, "available": e.available()} for e in self._engines
        ]

    def _pick_engine(self) -> OCREngine:
        for engine in self._engines:
            if engine.available():
                return engine
        raise OCREngineNotAvailable(
            "The PDF appears to be scanned and OCR is required, but no OCR engine "
            "is installed. Install Tesseract OCR (https://github.com/UB-Mannheim/"
            "tesseract/wiki) and set TESSERACT_CMD if needed."
        )

    def ocr_pdf(
        self,
        pdf_path: Path,
        page_renderer,
        progress_callback=None,
        page_indices: list[int] | None = None,
        language: str = "eng",
    ) -> list[tuple[int, str]]:
        """OCR selected pages (default: all).

        ``page_renderer(path, page_index) -> png_bytes`` decouples this manager
        from the PDF library.

        Returns list of (page_index, text). Structure detection happens in the
        analyzer; OCR output is grouped into paragraphs per page.
        """
        engine = self._pick_engine()
        from app.services.document.pdf_extractor import page_count

        total = page_count(pdf_path)
        indices = page_indices if page_indices is not None else list(range(total))
        results: list[tuple[int, str]] = []
        for i, pno in enumerate(indices):
            png = page_renderer(pdf_path, pno)
            text = engine.recognize_png(png, language=language)
            results.append((pno, text))
            if progress_callback:
                progress_callback(i + 1, len(indices))
            logger.info(
                "OCR page done",
                extra={
                    "operation": "ocr",
                    "status": "success",
                    "page": pno + 1,
                    "chars": len(text),
                },
            )
        return results

    @staticmethod
    def pages_to_blocks(pages: list[tuple[int, str]]) -> list[dict]:
        """Convert OCR page texts into paragraph-ish blocks with heading heuristics."""
        from app.services.document.structure import Block, HEADING, LIST_ITEM, PARAGRAPH

        blocks: list[Block] = []
        seq = 0
        for page_index, text in pages:
            page_no = page_index + 1
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
            for para in paragraphs:
                lines = [l.strip() for l in para.splitlines() if l.strip()]
                joined = " ".join(lines)
                first = lines[0] if lines else ""
                if len(lines) == 1 and len(first) <= 100 and (
                    _CHAPTER_RE.match(first) or (first.isupper() and any(c.isalpha() for c in first))
                ):
                    blocks.append(
                        Block(
                            seq=seq,
                            type=HEADING,
                            text=first,
                            level=1 if _CHAPTER_RE.match(first) else 2,
                            page=page_no,
                        )
                    )
                else:
                    blocks.append(Block(seq=seq, type=PARAGRAPH, text=joined, page=page_no))
                seq += 1
        return blocks
