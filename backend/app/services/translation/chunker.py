"""SmartChunker: structure-aware chunking for very large documents.

Splitting priority:
  1. Chapter boundaries (heading level 1)
  2. Section boundaries (heading levels 2-3)
  3. Paragraph boundaries
  4. Sentence boundaries (only for oversized paragraphs)

Rules:
  - A heading is never separated from its following content.
  - Tables are kept whole (row-splitting only as a last resort for huge tables).
  - List items are grouped and kept together where possible.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings
from app.services.document.structure import (
    Block,
    HEADING,
    LIST_ITEM,
    TABLE,
)
from app.utils.text import estimate_tokens, split_sentences


@dataclass
class SmartChunk:
    chunk_index: int
    chapter: str
    section: str
    page_start: int
    page_end: int
    blocks: list[Block] = field(default_factory=list)
    text: str = ""
    char_count: int = 0
    token_estimate: int = 0

    def render(self) -> str:
        parts: list[str] = []
        for b in self.blocks:
            parts.append(b.plain_text())
        self.text = "\n\n".join(p for p in parts if p)
        self.char_count = len(self.text)
        self.token_estimate = estimate_tokens(self.text)
        return self.text


class SmartChunker:
    def __init__(
        self,
        target_chars: int | None = None,
        max_chars: int | None = None,
    ):
        self.target = target_chars or settings.chunk_target_chars
        self.max = max_chars or settings.chunk_max_chars

    # ------------------------------------------------------------------
    def chunk(self, blocks: list[Block]) -> list[SmartChunk]:
        # Pre-split oversized paragraphs at sentence boundaries so the main
        # loop always deals with blocks that fit in a chunk.
        expanded = self._expand_oversized(blocks)

        chunks: list[SmartChunk] = []
        current: SmartChunk | None = None
        chapter = ""
        section = ""

        for block in expanded:
            if block.type == HEADING:
                if block.level == 1:
                    chapter = block.text.strip()[:500]
                    section = ""
                elif block.level <= 3:
                    section = block.text.strip()[:500]

            start_new = self._should_start_new_chunk(current, block)
            if start_new:
                if current is not None and current.blocks:
                    current.render()
                    chunks.append(current)
                current = SmartChunk(
                    chunk_index=len(chunks),
                    chapter=chapter,
                    section=section,
                    page_start=block.page,
                    page_end=block.page,
                )

            assert current is not None
            if block.type == TABLE and block.rows:
                self._add_table(current, block)
            elif block.type == HEADING:
                # Headings attach to the chunk that contains their content.
                current.blocks.append(block)
                current.char_count += len(block.text) + 2
                if block.level == 1:
                    current.chapter = chapter
                    current.section = ""
                elif block.level <= 3:
                    current.section = section
            else:
                # Paragraphs and list items (already size-bounded by _expand).
                current.blocks.append(block)
                current.char_count += len(block.plain_text()) + 2
            current.page_end = max(current.page_end, block.page)

        if current is not None and current.blocks:
            current.render()
            chunks.append(current)

        for i, c in enumerate(chunks):
            c.chunk_index = i
        return chunks

    # ------------------------------------------------------------------
    def _expand_oversized(self, blocks: list[Block]) -> list[Block]:
        expanded: list[Block] = []
        for block in blocks:
            text = block.text.strip() if block.type != TABLE else block.plain_text()
            if block.type != TABLE and len(text) > self.max:
                for piece in self._split_long_text(text, self.target):
                    expanded.append(
                        Block(
                            seq=block.seq,
                            type=block.type,
                            text=piece,
                            page=block.page,
                            level=block.level,
                            marker=block.marker,
                            bold=block.bold,
                            italic=block.italic,
                        )
                    )
            else:
                expanded.append(block)
        return expanded

    # ------------------------------------------------------------------
    def _should_start_new_chunk(self, current: SmartChunk | None, block: Block) -> bool:
        if current is None or not current.blocks:
            return current is None
        # Chapter boundaries always break.
        if block.type == HEADING and block.level == 1:
            return True
        # Heading must stay with following content: break only if we already have
        # meaningful content and adding the heading's section would overflow.
        if block.type == HEADING:
            return current.char_count + len(block.text) >= self.target
        # Never leave a heading alone at the end of a chunk.
        last = current.blocks[-1]
        if last.type == HEADING and current.char_count < self.target * 0.8:
            return False
        if current.char_count + len(block.plain_text()) > self.target:
            # Keep at least one content block with a trailing heading.
            if last.type == HEADING and len(current.blocks) == 1:
                return False
            return True
        return False

    # ------------------------------------------------------------------
    def _add_table(self, current: SmartChunk, block: Block) -> None:
        rendered = block.plain_text()
        if len(rendered) <= self.max:
            current.blocks.append(block)
            current.char_count += len(rendered) + 2
            return
        # Last resort for huge tables: split by row groups.
        rows = block.rows
        group: list[list[str]] = []
        group_len = 0
        for row in rows:
            row_len = sum(len(c) + 3 for c in row)
            if group and group_len + row_len > self.target:
                current.blocks.append(
                    Block(seq=block.seq, type=TABLE, text="", page=block.page, rows=group)
                )
                current.char_count += group_len + 2
                group = []
                group_len = 0
            group.append(row)
            group_len += row_len
        if group:
            current.blocks.append(
                Block(seq=block.seq, type=TABLE, text="", page=block.page, rows=group)
            )
            current.char_count += group_len + 2

    # ------------------------------------------------------------------
    @staticmethod
    def _split_long_text(text: str, target: int | None = None) -> list[str]:
        target = target or settings.chunk_target_chars
        sentences = split_sentences(text)
        if not sentences:
            return [text[i : i + target] for i in range(0, len(text), target)]
        pieces: list[str] = []
        buf: list[str] = []
        buf_len = 0
        for sentence in sentences:
            if buf and buf_len + len(sentence) + 1 > target:
                pieces.append(" ".join(buf))
                buf, buf_len = [], 0
            if len(sentence) > target:
                # Extremely long sentence: hard-split on word boundaries.
                words = sentence.split(" ")
                for w in words:
                    if buf_len + len(w) + 1 > target and buf:
                        pieces.append(" ".join(buf))
                        buf, buf_len = [], 0
                    buf.append(w)
                    buf_len += len(w) + 1
            else:
                buf.append(sentence)
                buf_len += len(sentence) + 1
        if buf:
            pieces.append(" ".join(buf))
        return pieces
