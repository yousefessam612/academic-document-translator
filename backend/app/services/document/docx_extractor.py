"""DOCX text extraction preserving structure, inline bold/italic, lists and tables."""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document as DocxDocument
from docx.document import Document as _DocxDocumentType
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.services.document.structure import Block, HEADING, LIST_ITEM, PARAGRAPH, TABLE

_HEADING_STYLE_RE = re.compile(r"heading\s*(\d)", re.IGNORECASE)


def _runs_to_marked_text(paragraph: Paragraph) -> tuple[str, bool, bool]:
    """Convert runs to text, wrapping bold/italic segments in ** / * markers."""
    parts: list[str] = []
    any_bold = False
    any_italic = False
    for run in paragraph.runs:
        text = run.text
        if not text:
            continue
        bold = bool(run.bold)
        italic = bool(run.italic)
        any_bold = any_bold or bold
        any_italic = any_italic or italic
        match = re.match(r"^(\s*)(.*?)(\s*)$", text, re.DOTALL)
        lead, core, trail = match.groups()
        if not core:
            parts.append(text)
        elif bold and italic:
            parts.append(f"{lead}***{core}***{trail}")
        elif bold:
            parts.append(f"{lead}**{core}**{trail}")
        elif italic:
            parts.append(f"{lead}*{core}*{trail}")
        else:
            parts.append(text)
    return "".join(parts), any_bold, any_italic


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = (paragraph.style.name if paragraph.style is not None else "") or ""
    m = _HEADING_STYLE_RE.match(style_name)
    if m:
        return min(4, max(1, int(m.group(1))))
    if style_name.lower() == "title":
        return 1
    return None


def _is_list(paragraph: Paragraph) -> bool:
    style_name = (paragraph.style.name if paragraph.style is not None else "") or ""
    if style_name.lower().startswith("list"):
        return True
    pPr = paragraph._p.find(qn("w:pPr"))
    if pPr is not None and pPr.find(qn("w:numPr")) is not None:
        return True
    return False


def _iter_body_elements(doc: _DocxDocumentType):
    """Yield (kind, element) in document order for paragraphs and tables."""
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl

    for child in doc.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield ("p", child)
        elif isinstance(child, CT_Tbl):
            yield ("tbl", child)


def extract_docx_blocks(path: Path) -> tuple[list[Block], dict]:
    """Extract structured blocks from a DOCX file."""
    doc = DocxDocument(str(path))
    blocks: list[Block] = []
    seq = 0
    total_chars = 0

    for kind, element in _iter_body_elements(doc):
        if kind == "p":
            paragraph = Paragraph(element, doc)
            text, any_bold, any_italic = _runs_to_marked_text(paragraph)
            text = text.strip()
            if not text:
                continue
            total_chars += len(text)
            level = _heading_level(paragraph)
            if level is not None:
                blocks.append(
                    Block(
                        seq=seq,
                        type=HEADING,
                        text=re.sub(r"\*+", "", text),
                        level=level,
                        page=-1,
                        bold=any_bold,
                        italic=any_italic,
                    )
                )
            elif _is_list(paragraph):
                blocks.append(Block(seq=seq, type=LIST_ITEM, text=text, marker="•"))
            else:
                blocks.append(
                    Block(
                        seq=seq,
                        type=PARAGRAPH,
                        text=text,
                        bold=any_bold,
                        italic=any_italic,
                    )
                )
            seq += 1
        else:  # table
            table = Table(element, doc)
            rows: list[list[str]] = []
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                rows.append(cells)
                total_chars += sum(len(c) for c in cells)
            if any(any(c for c in r) for r in rows):
                blocks.append(Block(seq=seq, type=TABLE, text="", rows=rows))
                seq += 1

    stats = {
        "page_count": None,
        "character_count": total_chars,
        "paragraph_count": sum(1 for b in blocks if b.type == PARAGRAPH),
    }
    return blocks, stats
