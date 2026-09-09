from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MessageOut(BaseModel):
    message: str
    data: dict[str, Any] | None = None


class ProviderStatusOut(BaseModel):
    configured: bool
    model: str | None = None
    base_url: str | None = None
    connected: bool | None = None
    detail: str | None = None


class DashboardOut(BaseModel):
    total_documents: int
    total_jobs: int
    completed_jobs: int
    active_jobs: int
    failed_jobs: int
    paused_jobs: int
    total_terms: int
    total_memory_entries: int
    recent_documents: list[dict[str, Any]]
    recent_jobs: list[dict[str, Any]]
