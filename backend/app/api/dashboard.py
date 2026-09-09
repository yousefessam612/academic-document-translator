"""Dashboard summary endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.job import TranslationJob
from app.models.memory import TranslationMemoryEntry
from app.models.terminology import Terminology
from app.schemas.common import DashboardOut
from app.services.jobs.manager import ACTIVE_STATUSES

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    total_docs = db.scalar(select(func.count(Document.id))) or 0
    total_jobs = db.scalar(select(func.count(TranslationJob.id))) or 0
    completed = db.scalar(
        select(func.count(TranslationJob.id)).where(TranslationJob.status == "completed")
    ) or 0
    active = db.scalar(
        select(func.count(TranslationJob.id)).where(TranslationJob.status.in_(ACTIVE_STATUSES))
    ) or 0
    failed = db.scalar(
        select(func.count(TranslationJob.id)).where(TranslationJob.status == "failed")
    ) or 0
    paused = db.scalar(
        select(func.count(TranslationJob.id)).where(TranslationJob.status == "paused")
    ) or 0
    terms = db.scalar(select(func.count(Terminology.id))) or 0
    memory_entries = db.scalar(select(func.count(TranslationMemoryEntry.id))) or 0

    recent_documents = [
        {
            "id": d.id,
            "filename": d.original_filename,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "status": d.status,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in db.scalars(select(Document).order_by(Document.created_at.desc()).limit(8))
    ]
    recent_jobs = [
        {
            "id": j.id,
            "document_id": j.document_id,
            "document_name": j.document.original_filename if j.document else None,
            "status": j.status,
            "progress_percentage": j.progress_percentage,
            "total_chunks": j.total_chunks,
            "completed_chunks": j.completed_chunks,
            "failed_chunks": j.failed_chunks,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            "error_message": j.error_message,
            "output_filename": j.output_filename,
        }
        for j in db.scalars(
            select(TranslationJob).order_by(TranslationJob.updated_at.desc()).limit(8)
        )
    ]
    return DashboardOut(
        total_documents=total_docs,
        total_jobs=total_jobs,
        completed_jobs=completed,
        active_jobs=active,
        failed_jobs=failed,
        paused_jobs=paused,
        total_terms=terms,
        total_memory_entries=memory_entries,
        recent_documents=recent_documents,
        recent_jobs=recent_jobs,
    )
