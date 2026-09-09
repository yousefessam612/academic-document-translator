from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

CHUNK_STATUSES = ("pending", "translating", "completed", "failed", "skipped")


class TranslationChunk(Base):
    __tablename__ = "translation_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("translation_jobs.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    job = relationship("TranslationJob", back_populates="chunks")

    chunk_index: Mapped[int] = mapped_column(Integer, index=True)

    chapter: Mapped[str] = mapped_column(String(500), default="")
    section: Mapped[str] = mapped_column(String(500), default="")

    page_start: Mapped[int] = mapped_column(Integer, default=-1)
    page_end: Mapped[int] = mapped_column(Integer, default=-1)

    source_text: Mapped[str] = mapped_column(Text)
    # Structural blocks belonging to this chunk (for DOCX reconstruction)
    source_blocks: Mapped[list | None] = mapped_column(JSON, nullable=True)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    char_count: Mapped[int] = mapped_column(Integer, default=0)
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens_used: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens_used: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
