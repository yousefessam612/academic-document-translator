from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Terminology(Base):
    __tablename__ = "terminology"
    __table_args__ = (
        UniqueConstraint("english_term", "domain", name="uq_term_english_domain"),
    )

    id: Mapped[str] = mapped_column(Integer, primary_key=True, autoincrement=True)
    english_term: Mapped[str] = mapped_column(String(300), index=True)
    arabic_term: Mapped[str] = mapped_column(String(300))
    domain: Mapped[str] = mapped_column(String(100), default="General", index=True)
    definition: Mapped[str] = mapped_column(Text, default="")
    alternatives: Mapped[list] = mapped_column(JSON, default=list)  # alternative Arabic translations
    notes: Mapped[str] = mapped_column(Text, default="")
    # preferred | allowed | avoid
    priority: Mapped[str] = mapped_column(String(20), default="preferred")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
