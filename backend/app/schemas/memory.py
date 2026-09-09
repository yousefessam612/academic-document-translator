from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class MemoryEntryIn(BaseModel):
    source_text: str = Field(min_length=1)
    target_text: str = Field(min_length=1)
    style: str = "Academic"
    domain: str = "General"


class MemoryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_text: str
    target_text: str
    target_language: str
    style: str
    domain: str
    use_count: int
    created_at: datetime | None = None
