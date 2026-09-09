from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

JOB_STATUSES = (
    "queued",
    "analyzing",
    "extracting",
    "ocr",
    "chunking",
    "translating",
    "assembling",
    "completed",
    "failed",
    "paused",
    "cancelled",
)


class TranslationJob(Base):
    __tablename__ = "translation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document = relationship("Document", lazy="joined")

    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0)
    completed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    current_chunk_index: Mapped[int] = mapped_column(Integer, default=-1)
    progress_percentage: Mapped[float] = mapped_column(default=0.0)

    # Per-job translation settings (style, domain, languages, dictionaries...)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)

    # Quality/consistency report produced before assembly
    quality_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    output_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    chunks = relationship(
        "TranslationChunk",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="TranslationChunk.chunk_index",
    )
