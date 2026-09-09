from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class TranslationMemoryEntry(Base):
    __tablename__ = "translation_memory"
    __table_args__ = (
        UniqueConstraint("source_hash", "target_language", name="uq_tm_source_target"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_hash: Mapped[str] = mapped_column(String(64), index=True)  # sha256 of normalized source
    source_text: Mapped[str] = mapped_column(Text)
    target_text: Mapped[str] = mapped_column(Text)
    target_language: Mapped[str] = mapped_column(String(10), default="ar")
    style: Mapped[str] = mapped_column(String(30), default="Academic")
    domain: Mapped[str] = mapped_column(String(100), default="General")

    document_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    similarity_score: Mapped[float] = mapped_column(default=1.0)
    use_count: Mapped[int] = mapped_column(Integer, default=0)
    approved: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
