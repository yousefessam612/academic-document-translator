from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255))  # sanitized display name
    stored_filename: Mapped[str] = mapped_column(String(255), unique=True)  # internal uuid name
    file_type: Mapped[str] = mapped_column(String(10))  # pdf | docx | txt
    mime_type: Mapped[str] = mapped_column(String(100), default="")
    file_size: Mapped[int] = mapped_column(Integer, default=0)  # bytes

    # uploaded | analyzing | analyzed | analysis_failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded")

    # Full analysis result (pages, char counts, scanned detection, estimates)
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Extracted structural blocks (list of {type, level, text, page, seq, ...})
    structure: Mapped[list | None] = mapped_column(JSON, nullable=True)

    title: Mapped[str] = mapped_column(String(500), default="")
    requires_ocr: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
