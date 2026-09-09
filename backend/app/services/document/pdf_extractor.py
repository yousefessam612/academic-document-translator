"""PDF text extraction with structure detection (PyMuPDF/fitz)."""
from __future__ import annotations

import io
import re
from collections import Counter
from pathlib import Path

import fitz

from app.core.logging_config import get_logger
from app.services.document.structure import Block, HEADING, LIST_ITEM, PARAGRAPH, TABLE

logger = get_logger(__name__)

_CHAPTER_RE = re.compile(r"^\s*(chapter|part|section|قسم|الفصل)\s+[\dIVXLC]+", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*([•▪◦‣·–—*]|\(?\d{1,2}[.)]|[a-z][.)])\s+")


def _in_any_bbox(rect, bboxes) -> bool:
    for x0, y0, x1, y1 in bboxes:
        if rect.x0 >= x0 - 2 and rect.y0 >= y0 - 2 and rect.x1 <= x1 + 2 and rect.y1 <= y1 + 2:
            return True
    return False


def _dominant_body_size(size_counter: Counter) -> float:
    if not size_counter:
        return 11.0
    return size_counter.most_common(1)[0][0]


def _heading_level(size: float, body: float) -> int:
    ratio = size / body if body else 1.0
    if ratio >= 1.7:
        return 1
    if ratio >= 1.4:
        return 2
    if ratio >= 1.15:
        return 3
    return 4


def extract_pdf_blocks(path: Path, page_start: int = 0, page_end: int | None = None) -> tuple[list[Block], dict]:
    """Extract structured blocks from a text-based PDF.

    Returns (blocks, stats) where stats includes page_count, character_count,
    and scanned-detection inputs.
    """
    doc = fitz.open(path)
    try:
        page_end = len(doc) if page_end is None else min(page_end, len(doc))
        size_counter: Counter = Counter()

        # --- First pass over sampled pages: find dominant body font size ---
        sample_indices = list(range(page_start, page_end))
        if len(sample_indices) > 20:
            step = max(1, len(sample_indices) // 20)
            sample_indices = sample_indices[::step][:20]
        for pno in sample_indices:
            page = doc[pno]
            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        n_chars = len(span.get("text", "").strip())
                        if n_chars:
                            size_counter[round(span["size"], 1)] += n_chars
        body_size = _dominant_body_size(size_counter)

        # --- Second pass: build blocks ---
        blocks: list[Block] = []
        seq = 0
        total_chars = 0
        image_pages = 0
        for pno in range(page_start, page_end):
            page = doc[pno]
            page_no = pno + 1

            # Tables first (so their text is not duplicated as paragraphs).
            table_bboxes: list[tuple] = []
            try:
                tabs = page.find_tables()
                for t in (tabs.tables or []):
                    rows = [[(cell or "").strip() for cell in row] for row in t.extract()]
                    rows = [r for r in rows if any(c for c in r)]
                    if len(rows) >= 2 and any(any(c for c in r) for r in rows):
                        table_bboxes.append(t.bbox)
                        blocks.append(
                            Block(seq=seq, type=TABLE, text="", page=page_no, rows=rows)
                        )
                        seq += 1
            except Exception:  # pragma: no cover - table finder robustness
                pass

            if page.get_images(full=False):
                image_pages += 1

            for block in page.get_text("dict")["blocks"]:
                if block.get("type") != 0:
                    continue
                bbox = block.get("bbox", (0, 0, 0, 0))
                if _in_any_bbox(fitz.Rect(bbox), table_bboxes):
                    continue  # already captured as a table
                # Merge lines of the block.
                lines: list[str] = []
                max_size = 0.0
                for line in block.get("lines", []):
                    line_text = "".join(span["text"] for span in line.get("spans", []))
                    for span in line.get("spans", []):
                        max_size = max(max_size, span.get("size", 0))
                    lines.append(line_text)
                text = "\n".join(lines).strip()
                if not text:
                    continue
                total_chars += len(text)

                single_line = len(lines) == 1 and "\n" not in text
                is_chapter = bool(_CHAPTER_RE.match(text))
                short = len(text) <= 150

                if single_line and short and (max_size >= body_size * 1.12 or is_chapter):
                    level = _heading_level(max_size, body_size)
                    if is_chapter and level > 1:
                        level = 1
                    blocks.append(
                        Block(
                            seq=seq,
                            type=HEADING,
                            text=text,
                            page=page_no,
                            level=level,
                        )
                    )
                    seq += 1
                    continue

                # Bullet-list detection.
                bullet = _BULLET_RE.match(text)
                if bullet and len(text) < 600:
                    blocks.append(
                        Block(
                            seq=seq,
                            type=LIST_ITEM,
                            text=_BULLET_RE.sub("", text).strip(),
                            page=page_no,
                            marker=bullet.group(1),
                        )
                    )
                    seq += 1
                    continue

                blocks.append(Block(seq=seq, type=PARAGRAPH, text=text, page=page_no))
                seq += 1

        stats = {
            "page_count": page_end - page_start,
            "character_count": total_chars,
            "image_pages": image_pages,
            "body_font_size": body_size,
        }
        return blocks, stats
    finally:
        doc.close()


def is_scanned_pdf(path: Path, sample_pages: int = 10, min_chars_per_page: float = 40.0) -> tuple[bool, dict]:
    """Heuristic scanned-PDF detection.

    A PDF is 'potentially scanned' when its sampled pages contain almost no
    extractable text but do contain images.
    """
    doc = fitz.open(path)
    try:
        n = len(doc)
        sample = min(n, sample_pages)
        chars = 0
        images = 0
        for pno in range(sample):
            page = doc[pno]
            chars += len(page.get_text("text").strip())
            if page.get_images(full=False):
                images += 1
        avg_chars = chars / sample if sample else 0.0
        scanned = sample > 0 and avg_chars < min_chars_per_page
        info = {
            "pages_sampled": sample,
            "avg_chars_per_page": round(avg_chars, 1),
            "pages_with_images": images,
        }
        return scanned, info
    finally:
        doc.close()


def render_page_to_png(path: Path, page_index: int, dpi: int = 200) -> bytes:
    """Render one PDF page to PNG bytes (input for OCR)."""
    doc = fitz.open(path)
    try:
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")
    finally:
        doc.close()


def page_count(path: Path) -> int:
    doc = fitz.open(path)
    try:
        return len(doc)
    finally:
        doc.close()
