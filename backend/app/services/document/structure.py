"""Intermediate document structure: an ordered list of typed blocks.

Every extractor (PDF / DOCX / TXT / OCR) produces ``list[Block]`` so the
chunker and assembler only deal with one representation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

HEADING = "heading"
PARAGRAPH = "paragraph"
LIST_ITEM = "list_item"
TABLE = "table"


@dataclass
class Block:
    seq: int
    type: str  # heading | paragraph | list_item | table
    text: str
    page: int = -1
    level: int = 0  # heading level (1=chapter ... 4=sub-subsection)
    marker: str = ""  # list bullet/marker
    rows: list[list[str]] = field(default_factory=list)  # table rows
    bold: bool = False
    italic: bool = False

    @property
    def is_heading(self) -> bool:
        return self.type == HEADING

    def plain_text(self) -> str:
        """Text representation used for translation (tables become pipe rows)."""
        if self.type == TABLE:
            return "\n".join(" | ".join(cell for cell in row) for row in self.rows)
        return self.text


def blocks_to_json(blocks: list[Block]) -> list[dict[str, Any]]:
    return [asdict(b) for b in blocks]


def blocks_from_json(data: list[dict[str, Any]] | None) -> list[Block]:
    if not data:
        return []
    blocks: list[Block] = []
    for i, item in enumerate(data):
        try:
            blocks.append(Block(**item))
        except TypeError:
            # Tolerate schema drift: build from known keys.
            blocks.append(
                Block(
                    seq=item.get("seq", i),
                    type=item.get("type", PARAGRAPH),
                    text=item.get("text", ""),
                    page=item.get("page", -1),
                    level=item.get("level", 0),
                    marker=item.get("marker", ""),
                    rows=item.get("rows", []),
                    bold=item.get("bold", False),
                    italic=item.get("italic", False),
                )
            )
    return blocks


def count_blocks(blocks: list[Block]) -> dict[str, int]:
    counts = {"headings": 0, "paragraphs": 0, "list_items": 0, "tables": 0}
    for b in blocks:
        if b.type == HEADING:
            counts["headings"] += 1
        elif b.type == PARAGRAPH:
            counts["paragraphs"] += 1
        elif b.type == LIST_ITEM:
            counts["list_items"] += 1
        elif b.type == TABLE:
            counts["tables"] += 1
    return counts


def detect_title(blocks: list[Block], fallback: str) -> str:
    """First significant heading, or the first non-empty paragraph if very short."""
    for b in blocks:
        if b.type == HEADING and b.level <= 2 and b.text.strip():
            return b.text.strip()[:300]
    for b in blocks:
        if b.text.strip() and len(b.text.strip()) <= 120:
            return b.text.strip()[:300]
    return fallback
