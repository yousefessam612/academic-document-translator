from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JobSettingsIn(BaseModel):
    source_language: str = "English"
    target_language: str = "Arabic"
    style: str = Field(default="Academic")
    domain: str = Field(default="General")
    use_global_dictionary: bool = True
    use_domain_dictionary: bool = True
    use_custom_dictionary: bool = True
    use_translation_memory: bool = True
    chunk_target_chars: int | None = None
    retranslate_completed: bool = False
    use_ocr_if_needed: bool = True


class JobStartRequest(BaseModel):
    settings: JobSettingsIn = Field(default_factory=JobSettingsIn)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    status: str
    total_chunks: int
    completed_chunks: int
    failed_chunks: int
    current_chunk_index: int
    progress_percentage: float
    settings: dict[str, Any] = {}
    quality_report: dict[str, Any] | None = None
    output_filename: str | None = None
    started_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    document_name: str | None = None


class JobProgressOut(BaseModel):
    job_id: str
    document_id: str
    document_name: str | None = None
    status: str
    total_chunks: int
    completed_chunks: int
    failed_chunks: int
    current_chunk_index: int
    current_chapter: str | None = None
    current_section: str | None = None
    progress_percentage: float
    eta_seconds: float | None = None
    error_message: str | None = None
    recent_errors: list[dict[str, Any]] = []
    consistency_issues: list[dict[str, Any]] = []


class JobListOut(BaseModel):
    jobs: list[JobOut]
    total: int
