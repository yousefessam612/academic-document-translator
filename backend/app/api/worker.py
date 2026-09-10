"""Remote worker API: lets a trusted machine (home IP) translate chunks for a
cloud deployment.

Why: AgentRouter's Aliyun WAF blocks chat-completions POSTs from datacenter
IPs (it serves an HTML JS-challenge instead of JSON). Everything else about
the cloud deployment works. In worker mode the cloud app keeps full control
(jobs, context building, validation, TM, consistency, assembly) and only the
LLM call itself is relayed through a worker running on a trusted network.

Auth: the site password (APP_ACCESS_PASSWORD, as HTTP Basic) PLUS the
X-Worker-Key header matching WORKER_API_KEY.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.database import SessionLocal, get_db
from app.models.chunk import TranslationChunk
from app.models.document import Document
from app.models.error import ProcessingError
from app.models.job import TranslationJob
from app.services.terminology.memory import TranslationMemoryService
from app.services.translation.agentrouter_provider import AgentRouterProvider
from app.services.translation.engine import (
    TranslationEngine,
    TranslationValidationError,
)
from app.services.translation.prompt_builder import strip_row_markers

logger = get_logger(__name__)
router = APIRouter(prefix="/worker", tags=["worker"])

# Cloud-side engine: context building + validation only (no LLM calls here).
_engine: TranslationEngine | None = None


def _get_engine() -> TranslationEngine:
    global _engine
    if _engine is None:
        _engine = TranslationEngine(AgentRouterProvider())
    return _engine


def _check_worker_key(request: Request, x_worker_key: str | None) -> None:
    """Worker endpoints require the site password (Basic auth middleware)
    plus the dedicated worker key."""
    if not settings.worker_mode:
        raise HTTPException(status_code=404, detail="Worker mode is not enabled on this server.")
    if not settings.worker_api_key:
        raise HTTPException(status_code=503, detail="WORKER_API_KEY is not configured on the server.")
    expected = settings.worker_api_key
    if x_worker_key is None or not x_worker_key.strip() or x_worker_key.strip() != expected:
        raise HTTPException(status_code=401, detail="Invalid worker key.")


class ClaimRequest(BaseModel):
    limit: int = Field(default=4, ge=1, le=16)


class TaskOut(BaseModel):
    chunk_id: str
    job_id: str
    chunk_index: int
    messages: list[dict]
    source_text: str
    attempts_done: int = 0


class ClaimOut(BaseModel):
    tasks: list[TaskOut]
    jobs_waiting: int


class ResultRequest(BaseModel):
    chunk_id: str
    ok: bool
    translation: str | None = None
    error: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts_done: int = 1
    # On validation rejection the worker may immediately retry with the
    # corrective message list produced by the server.
    retry_messages: list[dict] | None = None


class ResultOut(BaseModel):
    accepted: bool
    retry_messages: list[dict] | None = None
    error: str | None = None
    job_completed: bool = False


@router.get("/status")
def worker_status(request: Request, x_worker_key: str | None = Header(default=None)):
    _check_worker_key(request, x_worker_key)
    with SessionLocal() as db:
        jobs = list(
            db.scalars(select(TranslationJob).where(TranslationJob.status == "translating"))
        )
        pending = 0
        for job in jobs:
            pending += len(
                list(
                    db.scalars(
                        select(TranslationChunk.id).where(
                            TranslationChunk.job_id == job.id,
                            TranslationChunk.status.in_(("pending", "failed", "translating")),
                        )
                    )
                )
            )
        return {"mode": "worker", "jobs_translating": len(jobs), "chunks_open": pending}


@router.post("/claim", response_model=ClaimOut)
def claim_tasks(
    payload: ClaimRequest,
    request: Request,
    x_worker_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Claim pending chunks (marked 'translating') with fully built prompts."""
    _check_worker_key(request, x_worker_key)
    limit = payload.limit or settings.worker_claim_limit
    engine = _get_engine()

    jobs = list(
        db.scalars(
            select(TranslationJob)
            .where(TranslationJob.status == "translating")
            .order_by(TranslationJob.updated_at)
        )
    )
    tasks: list[TaskOut] = []
    for job in jobs:
        job_settings = job.settings or {}
        document = db.get(Document, job.document_id)
        if document is None:
            continue
        chunks = list(
            db.scalars(
                select(TranslationChunk)
                .where(TranslationChunk.job_id == job.id)
                .order_by(TranslationChunk.chunk_index)
            )
        )
        by_index = {c.chunk_index: c for c in chunks}
        remaining = limit - len(tasks)
        for chunk in chunks:
            if remaining <= 0:
                break
            if chunk.status != "pending":
                continue
            prev_chunk = by_index.get(chunk.chunk_index - 1)
            next_chunk = by_index.get(chunk.chunk_index + 1)
            ctx = engine.build_chunk_context(
                db,
                chunk,
                document.title or document.original_filename,
                job_settings,
                prev_chunk,
                next_chunk,
            )
            messages = engine.prompt_builder.build_messages(chunk.source_text, ctx)
            chunk.status = "translating"
            tasks.append(
                TaskOut(
                    chunk_id=chunk.id,
                    job_id=job.id,
                    chunk_index=chunk.chunk_index,
                    messages=messages,
                    source_text=chunk.source_text,
                )
            )
            remaining -= 1
        if remaining <= 0:
            break
    if tasks:
        db.commit()
    return ClaimOut(tasks=tasks, jobs_waiting=len(jobs))


def _load_chunk_job(db: Session, chunk_id: str) -> tuple[TranslationChunk | None, TranslationJob | None]:
    chunk = db.get(TranslationChunk, chunk_id)
    if chunk is None:
        return None, None
    return chunk, db.get(TranslationJob, chunk.job_id)


@router.post("/result", response_model=ResultOut)
def submit_result(
    payload: ResultRequest,
    request: Request,
    x_worker_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Worker posts a translation result; the server validates and persists.

    On validation failure the server returns corrective retry_messages so the
    worker can retry immediately without a fresh claim.
    """
    _check_worker_key(request, x_worker_key)
    chunk, job = _load_chunk_job(db, payload.chunk_id)
    if chunk is None or job is None:
        raise HTTPException(status_code=404, detail="Chunk not found.")
    if chunk.status == "completed":
        return ResultOut(accepted=True, job_completed=False)

    engine = _get_engine()

    # --- failure path ---
    if not payload.ok or not payload.translation or not payload.translation.strip():
        message = (payload.error or "Worker reported failure")[:900]
        chunk.status = "failed"
        chunk.attempts = (chunk.attempts or 0) + 1
        chunk.error_message = message
        job.failed_chunks = (job.failed_chunks or 0) + 1
        db.add(
            ProcessingError(
                job_id=job.id,
                document_id=chunk.document_id,
                chunk_id=chunk.id,
                chunk_index=chunk.chunk_index,
                error_type="worker_error",
                message=message,
            )
        )
        _refresh_progress(db, job)
        db.commit()
        return ResultOut(accepted=False, error=message)

    translation = payload.translation
    # Worker may retry in-place with the corrective messages; strip markers
    # exactly like the local engine does.
    if payload.retry_messages is None:
        # First submission for this claim: validate; reject -> corrective turn.
        try:
            engine.validate_translation(chunk.source_text, translation)
        except TranslationValidationError as exc:
            retry_messages = engine.prompt_builder.build_messages(chunk.source_text, _ctx_for(db, chunk, job))
            retry_messages.append({"role": "assistant", "content": translation})
            retry_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous output was rejected: {exc.message}\n"
                        "Please output the complete translation again, following ALL "
                        "rules exactly: same paragraph count with blank lines between "
                        "paragraphs, every table row keeping its exact [n] marker in "
                        "order, Arabic output only."
                    ),
                }
            )
            return ResultOut(accepted=False, retry_messages=retry_messages, error=exc.message)

    translation = strip_row_markers(translation)
    if not translation.strip():
        chunk.status = "failed"
        chunk.error_message = "Empty translation after cleanup"
        job.failed_chunks = (job.failed_chunks or 0) + 1
        _refresh_progress(db, job)
        db.commit()
        return ResultOut(accepted=False, error="empty translation")

    # --- success path (mirrors JobManager._translate_single) ---
    job_settings = job.settings or {}
    chunk.translation = translation
    chunk.status = "completed"
    chunk.error_message = None
    chunk.prompt_tokens_used = payload.prompt_tokens or 0
    chunk.completion_tokens_used = payload.completion_tokens or 0
    chunk.attempts = payload.attempts_done or 1
    job.completed_chunks = (job.completed_chunks or 0) + 1
    job.current_chunk_index = chunk.chunk_index

    # per-chunk consistency warnings
    ctx = _ctx_for(db, chunk, job)
    if ctx.terminology:
        for issue in engine.consistency.check_chunk(
            chunk.source_text, translation, chunk.chunk_index, ctx.terminology
        )[:20]:
            db.add(
                ProcessingError(
                    job_id=job.id,
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    error_type="consistency",
                    severity="warning",
                    message=issue["message"],
                )
            )
    db.commit()

    if job_settings.get("use_translation_memory", True):
        try:
            tm = TranslationMemoryService(db)
            tm.store(
                source_text=chunk.source_text,
                target_text=translation,
                style=job_settings.get("style", "Academic"),
                domain=job_settings.get("domain", "General"),
                document_id=chunk.document_id,
                job_id=job.id,
            )
        except Exception:  # pragma: no cover — TM must not break jobs
            logger.warning("TM store failed", extra={"operation": "tm_store", "status": "error"})

    _refresh_progress(db, job)
    db.commit()

    logger.info(
        "Worker chunk translated",
        extra={
            "job_id": job.id,
            "chunk_index": chunk.chunk_index,
            "operation": "worker_result",
            "status": "success",
        },
    )
    return ResultOut(accepted=True)


def _ctx_for(db: Session, chunk: TranslationChunk, job: TranslationJob):
    engine = _get_engine()
    document = db.get(Document, chunk.document_id)
    prev_chunk = db.scalars(
        select(TranslationChunk).where(
            TranslationChunk.job_id == job.id,
            TranslationChunk.chunk_index == chunk.chunk_index - 1,
        )
    ).first()
    next_chunk = db.scalars(
        select(TranslationChunk).where(
            TranslationChunk.job_id == job.id,
            TranslationChunk.chunk_index == chunk.chunk_index + 1,
        )
    ).first()
    return engine.build_chunk_context(
        db,
        chunk,
        (document.title or document.original_filename) if document else "Document",
        job.settings or {},
        prev_chunk,
        next_chunk,
    )


def _refresh_progress(db: Session, job: TranslationJob) -> None:
    done = job.completed_chunks or 0
    failed = job.failed_chunks or 0
    total = job.total_chunks or 0
    job.progress_percentage = round((done + failed) / total * 100, 1) if total else 0.0
