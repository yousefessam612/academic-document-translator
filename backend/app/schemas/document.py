from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_filename: str
    file_type: str
    file_size: int
    status: str
    title: str
    requires_ocr: bool
    created_at: datetime | None = None
    analysis: dict[str, Any] | None = None


class DocumentAnalysisOut(BaseModel):
    file_type: str
    file_size: int
    page_count: int | None = None
    has_extractable_text: bool
    is_scanned: bool
    ocr_used: bool
    character_count: int
    heading_count: int
    paragraph_count: int
    table_count: int
    list_item_count: int
    estimated_translation_units: int
    estimated_chunks: int
    chapters: list[str] = []


class DocumentDetailOut(DocumentOut):
    structure_summary: dict[str, Any] | None = None


class DocumentListOut(BaseModel):
    documents: list[DocumentOut]
    total: int
