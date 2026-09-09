from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class ProcessingError(Base):
    __tablename__ = "processing_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    document_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # api_error | auth_error | rate_limit | invalid_response | validation | ocr_error | assembly | consistency
    error_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="error")  # error | warning
    message: Mapped[str] = mapped_column(Text)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
