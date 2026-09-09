from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TerminologyIn(BaseModel):
    english_term: str = Field(min_length=1, max_length=300)
    arabic_term: str = Field(min_length=1, max_length=300)
    domain: str = "General"
    definition: str = ""
    alternatives: list[str] = []
    notes: str = ""
    priority: str = "preferred"
    active: bool = True


class TerminologyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    english_term: str
    arabic_term: str
    domain: str
    definition: str
    alternatives: list[str] = []
    notes: str
    priority: str
    active: bool
    created_at: datetime | None = None


class TerminologyUpdateIn(BaseModel):
    english_term: str | None = None
    arabic_term: str | None = None
    domain: str | None = None
    definition: str | None = None
    alternatives: list[str] | None = None
    notes: str | None = None
    priority: str | None = None
    active: bool | None = None


class TerminologyImportResult(BaseModel):
    imported: int
    updated: int
    skipped_duplicates: int
    errors: list[str]
