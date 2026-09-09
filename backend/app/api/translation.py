"""Translation job endpoints: start/pause/resume/cancel/progress."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.document import Document
from app.models.job import TranslationJob
from app.schemas.job import JobListOut, JobOut, JobStartRequest
from app.services.jobs.manager import JobManager

router = APIRouter(prefix="/translation", tags=["translation"])


def get_manager(request: Request) -> JobManager:
    return request.app.state.jobs


@router.post("/{document_id}/start", response_model=JobOut, status_code=201)
async def start_translation(
    document_id: str,
    request: Request,
    body: JobStartRequest | None = None,
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    manager: JobManager = get_manager(request)
    settings_in = body.settings if body and body.settings else None
    try:
        job, created = manager.start_job(document_id, settings_in)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not created:
        # Existing active/paused job for this document.
        return job
    return job


@router.get("/jobs", response_model=JobListOut)
def list_jobs(
    document_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(TranslationJob).order_by(TranslationJob.updated_at.desc())
    if document_id:
        stmt = stmt.where(TranslationJob.document_id == document_id)
    jobs = list(db.scalars(stmt.offset(offset).limit(min(limit, 200))))
    total = len(list(db.scalars(select(TranslationJob.id))))
    out = []
    for job in jobs:
        item = JobOut.model_validate(job)
        item.document_name = job.document.original_filename if job.document else None
        out.append(item)
    return JobListOut(jobs=out, total=total)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.get(TranslationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    out = JobOut.model_validate(job)
    out.document_name = job.document.original_filename if job.document else None
    return out


@router.get("/jobs/{job_id}/chunks")
def get_job_chunks(
    job_id: str,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    from app.models.chunk import TranslationChunk

    job = db.get(TranslationJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    stmt = select(TranslationChunk).where(TranslationChunk.job_id == job_id)
    if status:
        stmt = stmt.where(TranslationChunk.status == status)
    stmt = stmt.order_by(TranslationChunk.chunk_index)
    chunks = list(db.scalars(stmt.offset(offset).limit(min(limit, 500))))
    return {
        "total": job.total_chunks,
        "completed": job.completed_chunks,
        "failed": job.failed_chunks,
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "status": c.status,
                "chapter": c.chapter,
                "section": c.section,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "char_count": c.char_count,
                "attempts": c.attempts,
                "error_message": c.error_message,
                "source_preview": c.source_text[:200],
                "translation_preview": (c.translation or "")[:200],
            }
            for c in chunks
        ],
    }


@router.post("/jobs/{job_id}/pause")
async def pause_translation(job_id: str, request: Request):
    manager: JobManager = get_manager(request)
    if not manager.pause_job(job_id):
        raise HTTPException(status_code=409, detail="Job is not currently running.")
    return {"message": "Pause requested. In-flight chunks will finish first."}


@router.post("/jobs/{job_id}/resume", response_model=JobOut)
async def resume_translation(job_id: str, request: Request, db: Session = Depends(get_db)):
    manager: JobManager = get_manager(request)
    job = manager.resume_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    out = JobOut.model_validate(job)
    out.document_name = job.document.original_filename if job.document else None
    return out


@router.post("/jobs/{job_id}/cancel")
async def cancel_translation(job_id: str, request: Request):
    manager: JobManager = get_manager(request)
    if not manager.cancel_job(job_id):
        raise HTTPException(status_code=409, detail="Job cannot be cancelled in its current state.")
    return {"message": "Cancel requested."}


@router.post("/jobs/{job_id}/retry-failed", response_model=JobOut)
async def retry_failed(job_id: str, request: Request, db: Session = Depends(get_db)):
    manager: JobManager = get_manager(request)
    job = manager.retry_failed_chunks(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    out = JobOut.model_validate(job)
    out.document_name = job.document.original_filename if job.document else None
    return out


@router.get("/jobs/{job_id}/progress")
def get_progress(job_id: str, request: Request):
    manager: JobManager = get_manager(request)
    progress = manager.get_progress(job_id)
    if progress is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return progress
