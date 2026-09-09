from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AppSettings(Base):
    """Singleton row (id=1) holding application default translation settings."""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    source_language: Mapped[str] = mapped_column(String(30), default="English")
    target_language: Mapped[str] = mapped_column(String(30), default="Arabic")
    style: Mapped[str] = mapped_column(String(30), default="Academic")
    domain: Mapped[str] = mapped_column(String(100), default="General")
    chunk_target_chars: Mapped[int] = mapped_column(Integer, default=4000)
    use_global_dictionary: Mapped[bool] = mapped_column(default=True)
    use_domain_dictionary: Mapped[bool] = mapped_column(default=True)
    use_custom_dictionary: Mapped[bool] = mapped_column(default=True)
    use_translation_memory: Mapped[bool] = mapped_column(default=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
