"""ContextManager: builds bounded context around each chunk.

Sends only what is useful and within limits:
  - document title, current chapter/section titles
  - a tail of the previous chunk's source text
  - a head of the next chunk's source text
  - terminology + translation-memory matches (via the engine)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import settings


@dataclass
class ChunkContext:
    document_title: str = ""
    chapter: str = ""
    section: str = ""
    previous_text: str = ""  # tail of previous chunk (source language)
    next_text: str = ""  # head of next chunk (source language)
    previous_translation_tail: str = ""  # tail of previous chunk translation (Arabic)
    terminology: list[dict] = field(default_factory=list)
    memory_matches: list[dict] = field(default_factory=list)
    target_language: str = "Arabic"
    style: str = "Academic"
    domain: str = "General"


class ContextManager:
    def __init__(self, max_context_chars: int | None = None):
        self.max_chars = max_context_chars or settings.context_chars

    def build(
        self,
        document_title: str,
        chapter: str,
        section: str,
        previous_chunk_text: str | None,
        previous_chunk_translation: str | None,
        next_chunk_text: str | None,
    ) -> ChunkContext:
        ctx = ChunkContext(document_title=document_title, chapter=chapter, section=section)
        budget = self.max_chars
        if previous_chunk_text:
            ctx.previous_text = previous_chunk_text[-budget:]
        if next_chunk_text:
            ctx.next_text = next_chunk_text[: budget // 2]
        if previous_chunk_translation:
            # A short glance at the established Arabic phrasing improves consistency.
            ctx.previous_translation_tail = previous_chunk_translation[-(budget // 2) :]
        return ctx
