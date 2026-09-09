"""Background translation job manager.

- Jobs run as asyncio tasks inside the API process (no external broker needed).
- Every chunk state change is persisted to SQLite immediately, so an
  interrupted job (app restart, crash) can be resumed without re-translating
  completed chunks.
- Pause/resume/cancel are cooperative: in-flight chunks finish, then the
  runner parks (pause) or stops (cancel).
- Concurrency is bounded (MAX_CONCURRENT_TRANSLATIONS).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.database import SessionLocal
from app.models.chunk import TranslationChunk
from app.models.document import Document
from app.models.error import ProcessingError
from app.models.job import TranslationJob
from app.schemas.job import JobSettingsIn
from app.services.document.analyzer import AnalysisError, DocumentAnalyzer
from app.services.document.structure import blocks_from_json, blocks_to_json
from app.services.export.assembler import AssemblyError, DocumentAssembler
from app.services.terminology.memory import TranslationMemoryService
from app.services.terminology.service import TerminologyService
from app.services.translation.agentrouter_provider import AgentRouterProvider
from app.services.translation.chunker import SmartChunker
from app.services.translation.consistency import ConsistencyChecker
from app.services.translation.engine import TranslationEngine
from app.services.translation.provider import (
    AuthenticationError,
    ProviderError,
    ProviderNotConfiguredError,
)
from app.utils.files import unique_output_name

logger = get_logger(__name__)

ACTIVE_STATUSES = {
    "queued", "analyzing", "extracting", "ocr", "chunking", "translating", "assembling",
}
RESUMABLE_STATUSES = {"paused", "failed", "cancelled"}


@dataclass
class JobHandle:
    job_id: str
    task: asyncio.Task | None = None
    pause_event: asyncio.Event = field(default_factory=asyncio.Event)
    pause_requested: bool = False
    cancel_requested: bool = False

    def live(self) -> bool:
        return self.task is not None and not self.task.done()


class JobManager:
    def __init__(self, provider: AgentRouterProvider | None = None):
        self.provider = provider or AgentRouterProvider()
        self.handles: dict[str, JobHandle] = {}
        self._startup_recovered = False

    # ------------------------------------------------------------ lifecycle
    def recover_interrupted_jobs(self) -> int:
        """On startup, park jobs that were mid-flight (process died/restarted)."""
        if self._startup_recovered:
            return 0
        self._startup_recovered = True
        count = 0
        with SessionLocal() as db:
            jobs = list(
                db.scalars(select(TranslationJob).where(TranslationJob.status.in_(ACTIVE_STATUSES)))
            )
            for job in jobs:
                job.status = "paused"
                job.error_message = "Interrupted. You can resume this translation."
                count += 1
            db.commit()
        if count:
            logger.info(
                f"Recovered {count} interrupted jobs as paused",
                extra={"operation": "startup_recovery", "status": "success", "count": count},
            )
        return count

    # ------------------------------------------------------------- controls
    def start_job(self, document_id: str, job_settings: JobSettingsIn | None = None) -> tuple[TranslationJob, bool]:
        """Create and start a job. Returns (job, created_new)."""
        job_settings = job_settings or JobSettingsIn()
        with SessionLocal() as db:
            document = db.get(Document, document_id)
            if document is None:
                raise LookupError("Document not found.")
            existing = db.scalars(
                select(TranslationJob).where(
                    TranslationJob.document_id == document_id,
                    TranslationJob.status.in_(ACTIVE_STATUSES | {"paused"}),
                )
            ).first()
            if existing is not None:
                db.refresh(existing)
                return existing, False

            job = TranslationJob(
                id=uuid.uuid4().hex,
                document_id=document_id,
                status="queued",
                settings=job_settings.model_dump(),
                started_at=datetime.now(timezone.utc),
            )
            db.add(job)
            db.commit()
            db.refresh(job)
        self._spawn(job.id)
        return job, True

    def pause_job(self, job_id: str) -> bool:
        handle = self.handles.get(job_id)
        if handle and handle.live():
            handle.pause_requested = True
            return True
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job and job.status in ACTIVE_STATUSES:
                job.status = "paused"
                job.error_message = "Paused. You can resume this translation."
                db.commit()
                return True
        return False

    def resume_job(self, job_id: str) -> TranslationJob | None:
        handle = self.handles.get(job_id)
        if handle and handle.live():
            # Wake the parked runner; do NOT spawn a second one.
            handle.pause_requested = False
            handle.pause_event.set()
            with SessionLocal() as db:
                job = db.get(TranslationJob, job_id)
                if job:
                    job.status = "translating"
                    job.error_message = None
                    db.commit()
                    db.refresh(job)
                    return job
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return None
            if job.status not in RESUMABLE_STATUSES:
                return job
            job.status = "queued"
            job.error_message = None
            db.commit()
            db.refresh(job)
        self._spawn(job_id)
        return job

    def cancel_job(self, job_id: str) -> bool:
        handle = self.handles.get(job_id)
        if handle and handle.live():
            handle.cancel_requested = True
            handle.pause_requested = False
            handle.pause_event.set()  # wake a parked runner so it can exit
            return True
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job and job.status not in ("completed", "cancelled"):
                job.status = "cancelled"
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
                return True
        return False

    def retry_failed_chunks(self, job_id: str) -> TranslationJob | None:
        """Reset failed chunks to pending, then resume (retries only failures)."""
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return None
            failed = list(
                db.scalars(
                    select(TranslationChunk).where(
                        TranslationChunk.job_id == job_id,
                        TranslationChunk.status == "failed",
                    )
                )
            )
            for chunk in failed:
                chunk.status = "pending"
                chunk.error_message = None
            db.execute(
                update(TranslationJob)
                .where(TranslationJob.id == job_id)
                .values(failed_chunks=0)
            )
            db.commit()
        return self.resume_job(job_id)

    # -------------------------------------------------------------- runner
    def _spawn(self, job_id: str) -> None:
        handle = self.handles.get(job_id) or JobHandle(job_id=job_id)
        handle.pause_requested = False
        handle.cancel_requested = False
        handle.pause_event.clear()
        self.handles[job_id] = handle
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # Called outside a running loop (scripts/tests).
            handle.task = asyncio.run(self._run_job(job_id, handle))
            return
        handle.task = loop.create_task(self._run_job(job_id, handle))

    async def _run_job(self, job_id: str, handle: JobHandle) -> None:
        logger.info(
            "Job runner started",
            extra={"job_id": job_id, "operation": "job", "status": "started"},
        )
        try:
            await self._pipeline(job_id, handle)
        except Exception as exc:  # noqa: BLE001 — final safety net
            logger.exception(
                "Job crashed",
                extra={
                    "job_id": job_id,
                    "operation": "job",
                    "status": "error",
                    "error_type": type(exc).__name__,
                },
            )
            self._set_status(job_id, "failed", error_message=self._friendly(exc))
        finally:
            handle = self.handles.get(job_id)
            if handle and not handle.live():
                self.handles.pop(job_id, None)

    async def _pipeline(self, job_id: str, handle: JobHandle) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                raise LookupError("Job not found.")
            document = db.get(Document, job.document_id)
            if document is None:
                raise LookupError("Document not found.")
            job_settings = job.settings or {}
            retranslate = bool(job_settings.get("retranslate_completed", False))
            existing = list(
                db.scalars(
                    select(TranslationChunk).where(TranslationChunk.job_id == job_id)
                )
            )

        if retranslate and existing:
            with SessionLocal() as db:
                for chunk in db.scalars(
                    select(TranslationChunk).where(TranslationChunk.job_id == job_id)
                ):
                    db.delete(chunk)
                db.execute(
                    update(TranslationJob)
                    .where(TranslationJob.id == job_id)
                    .values(completed_chunks=0, failed_chunks=0, progress_percentage=0)
                )
                db.commit()
            existing = []

        if not existing:
            await self._analyze_and_chunk(job_id, document, job_settings)
            if handle.cancel_requested:
                self._set_status(job_id, "cancelled")
                return

        if not await self._translate_chunks(job_id, job_settings, handle):
            return  # fatal error already recorded on the job

        if handle.cancel_requested:
            self._set_status(job_id, "cancelled")
            return
        if handle.pause_requested:
            self._set_status(
                job_id, "paused", error_message="Paused. You can resume this translation."
            )
            await self._wait_for_resume(handle)
            if handle.cancel_requested:
                self._set_status(job_id, "cancelled")
                return
            # Continue the pipeline from persisted state (no re-chunking).
            return await self._pipeline_cont(job_id, handle)

        await self._finish_or_assemble(job_id)

    async def _pipeline_cont(self, job_id: str, handle: JobHandle) -> None:
        """Post-resume continuation: translate remaining chunks, then finish."""
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            job_settings = job.settings or {}
        if not await self._translate_chunks(job_id, job_settings, handle):
            return  # fatal error already recorded on the job
        if handle.cancel_requested:
            self._set_status(job_id, "cancelled")
            return
        if handle.pause_requested:
            self._set_status(
                job_id, "paused", error_message="Paused. You can resume this translation."
            )
            await self._wait_for_resume(handle)
            if handle.cancel_requested:
                self._set_status(job_id, "cancelled")
                return
            return await self._pipeline_cont(job_id, handle)
        await self._finish_or_assemble(job_id)

    async def _finish_or_assemble(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            if (job.failed_chunks or 0) > 0:
                self._set_status(
                    job_id,
                    "failed",
                    error_message=(
                        f"{job.failed_chunks} chunk(s) failed after "
                        f"{settings.max_retries} attempts. You can resume the "
                        "translation; failed chunks will be retried."
                    ),
                )
                return
        await self._assemble(job_id)

    # ----------------------------------------------------------- analysis
    async def _analyze_and_chunk(
        self, job_id: str, document: Document, job_settings: dict
    ) -> None:
        self._set_status(job_id, "analyzing")
        # If the automatic post-upload analysis is mid-run, wait for it instead
        # of extracting the same file twice.
        from app.services.document.analysis_runner import is_running

        for _ in range(900):
            if not is_running(document.id):
                break
            await asyncio.sleep(1)

        with SessionLocal() as db:
            fresh_doc = db.get(Document, document.id)
            needs_analysis = not fresh_doc.structure

        if needs_analysis:
            upload_path = settings.uploads_dir / document.stored_filename
            if not upload_path.exists():
                raise AnalysisError("The uploaded file is missing from storage.")

        if needs_analysis:
            def progress(status: str) -> None:
                if status.startswith("ocr"):
                    self._set_status(job_id, "ocr")
                elif status in ACTIVE_STATUSES:
                    self._set_status(job_id, status)

            analysis = await asyncio.to_thread(
                DocumentAnalyzer().analyze,
                upload_path,
                document.file_type,
                document.original_filename,
                progress,
                bool(job_settings.get("use_ocr_if_needed", True)),
            )
            structure = analysis.pop("structure", [])
            with SessionLocal() as db:
                doc = db.get(Document, document.id)
                doc.structure = structure
                doc.title = analysis.get("title", "")
                doc.analysis = analysis
                doc.requires_ocr = analysis.get("is_scanned", False)
                doc.status = "analyzed"
                db.commit()
        else:
            with SessionLocal() as db:
                doc = db.get(Document, document.id)
                structure = doc.structure or []

        blocks = blocks_from_json(structure)
        if not blocks:
            raise AnalysisError("No text content could be extracted from this document.")

        self._set_status(job_id, "chunking")
        chunker = SmartChunker(
            target_chars=job_settings.get("chunk_target_chars") or settings.chunk_target_chars
        )
        smart_chunks = await asyncio.to_thread(chunker.chunk, blocks)

        with SessionLocal() as db:
            for sc in smart_chunks:
                db.add(
                    TranslationChunk(
                        id=uuid.uuid4().hex,
                        job_id=job_id,
                        document_id=document.id,
                        chunk_index=sc.chunk_index,
                        chapter=sc.chapter,
                        section=sc.section,
                        page_start=sc.page_start,
                        page_end=sc.page_end,
                        source_text=sc.render(),
                        source_blocks=blocks_to_json(sc.blocks),
                        status="pending",
                        char_count=sc.char_count,
                        token_estimate=sc.token_estimate,
                    )
                )
            db.execute(
                update(TranslationJob)
                .where(TranslationJob.id == job_id)
                .values(
                    total_chunks=len(smart_chunks),
                    completed_chunks=0,
                    failed_chunks=0,
                )
            )
            db.commit()

    # --------------------------------------------------------- translation
    async def _translate_chunks(self, job_id: str, job_settings: dict, handle: JobHandle) -> bool:
        """Translate all pending/failed chunks. Returns False when a fatal
        error (already recorded on the job) stopped the run."""
        self._set_status(job_id, "translating")
        engine = TranslationEngine(self.provider)
        concurrency = max(1, settings.max_concurrent_translations)
        semaphore = asyncio.Semaphore(concurrency)
        window: list[asyncio.Task] = []
        translating_since = time.monotonic()

        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            total = job.total_chunks or 0
            document_id = job.document_id
            chunk_ids: list[tuple[str, int]] = [
                (c.id, c.chunk_index)
                for c in db.scalars(
                    select(TranslationChunk)
                    .where(TranslationChunk.job_id == job_id)
                    .order_by(TranslationChunk.chunk_index)
                )
            ]
        if total == 0:
            total = len(chunk_ids)

        async def translate_one(chunk_id: str, index: int) -> str | None:
            async with semaphore:
                return await self._translate_single(
                    engine, job_id, document_id, chunk_id, index, job_settings
                )

        for chunk_id, index in chunk_ids:
            if handle.cancel_requested or handle.pause_requested:
                break
            with SessionLocal() as db:
                chunk = db.get(TranslationChunk, chunk_id)
                if chunk is None or chunk.status == "completed":
                    continue

            while len(window) >= concurrency:
                if not await self._complete_oldest(window, job_id, total, translating_since):
                    return False
                if handle.cancel_requested or handle.pause_requested:
                    await self._drain(window, job_id, total, translating_since)
                    return True
            window.append(asyncio.create_task(translate_one(chunk_id, index)))

        return await self._drain(window, job_id, total, translating_since)

    async def _complete_oldest(
        self, window: list[asyncio.Task], job_id: str, total: int, since: float
    ) -> bool:
        """Await the oldest in-flight task. Returns False on fatal error."""
        if not window:
            return True
        task = window.pop(0)
        fatal_message = await task
        if fatal_message:
            self._set_status(job_id, "failed", error_message=fatal_message)
            for t in window:
                t.cancel()
            return False
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return False
            done = job.completed_chunks or 0
            failed = job.failed_chunks or 0
            processed = done + failed
            job.progress_percentage = round(processed / total * 100, 1) if total else 0.0
            elapsed = max(1.0, time.monotonic() - since)
            merged = dict(job.settings or {})
            if done >= 3:
                rate = done / elapsed
                merged["eta_seconds"] = round((total - processed) / max(rate, 1e-6), 0)
            else:
                merged["eta_seconds"] = None
            job.settings = merged
            db.commit()
        return True

    async def _drain(
        self, window: list[asyncio.Task], job_id: str, total: int, since: float
    ) -> bool:
        while window:
            if not await self._complete_oldest(window, job_id, total, since):
                return False
        return True

    async def _translate_single(
        self,
        engine: TranslationEngine,
        job_id: str,
        document_id: str,
        chunk_id: str,
        index: int,
        job_settings: dict,
    ) -> str | None:
        """Translate one chunk. Returns None on success, message on FATAL error."""
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, chunk_id)
            document = db.get(Document, document_id)
            if chunk is None or document is None:
                return None
            if chunk.status == "completed":
                return None
            prev_chunk = db.scalars(
                select(TranslationChunk).where(
                    TranslationChunk.job_id == job_id,
                    TranslationChunk.chunk_index == index - 1,
                )
            ).first()
            next_chunk = db.scalars(
                select(TranslationChunk).where(
                    TranslationChunk.job_id == job_id,
                    TranslationChunk.chunk_index == index + 1,
                )
            ).first()
            chunk.status = "translating"
            db.commit()
            ctx = engine.build_chunk_context(
                db,
                chunk,
                document.title or document.original_filename,
                job_settings,
                prev_chunk,
                next_chunk,
            )
            source_text = chunk.source_text

        started = time.monotonic()
        try:
            translation, info = await engine.translate_chunk(source_text, chunk_index=index, ctx=ctx)
        except AuthenticationError:
            with SessionLocal() as db2:
                db2.execute(
                    update(TranslationChunk)
                    .where(TranslationChunk.id == chunk_id)
                    .values(status="failed", error_message="Authentication failed")
                )
                db2.commit()
            logger.error(
                "Authentication failure — aborting job",
                extra={
                    "job_id": job_id,
                    "chunk_index": index,
                    "operation": "translate_chunk",
                    "status": "error",
                    "error_type": "auth",
                },
            )
            return (
                "Translation service authentication failed. "
                "Check your API configuration (AGENTROUTER_API_KEY)."
            )
        except ProviderNotConfiguredError as exc:
            with SessionLocal() as db2:
                db2.execute(
                    update(TranslationChunk)
                    .where(TranslationChunk.id == chunk_id)
                    .values(status="failed", error_message="Translation provider is not configured")
                )
                db2.commit()
            return str(exc) or exc.user_message
        except ProviderError as exc:
            with SessionLocal() as db2:
                db2.execute(
                    update(TranslationChunk)
                    .where(TranslationChunk.id == chunk_id)
                    .values(
                        status="failed",
                        attempts=TranslationChunk.attempts + 1,
                        error_message=str(exc)[:900],
                    )
                )
                db2.execute(
                    update(TranslationJob)
                    .where(TranslationJob.id == job_id)
                    .values(
                        failed_chunks=TranslationJob.failed_chunks + 1,
                        current_chunk_index=index,
                    )
                )
                db2.add(
                    ProcessingError(
                        job_id=job_id,
                        document_id=document_id,
                        chunk_id=chunk_id,
                        chunk_index=index,
                        error_type="api_error",
                        message=str(exc)[:1500],
                    )
                )
                db2.commit()
            logger.warning(
                "Chunk failed after retries",
                extra={
                    "job_id": job_id,
                    "chunk_index": index,
                    "operation": "translate_chunk",
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )
            return None
        except Exception as exc:  # noqa: BLE001 — unexpected per-chunk failure
            with SessionLocal() as db2:
                db2.execute(
                    update(TranslationChunk)
                    .where(TranslationChunk.id == chunk_id)
                    .values(
                        status="failed",
                        attempts=TranslationChunk.attempts + 1,
                        error_message=f"{type(exc).__name__}: {exc}"[:900],
                    )
                )
                db2.execute(
                    update(TranslationJob)
                    .where(TranslationJob.id == job_id)
                    .values(failed_chunks=TranslationJob.failed_chunks + 1)
                )
                db2.commit()
            logger.exception(
                "Unexpected chunk error",
                extra={
                    "job_id": job_id,
                    "chunk_index": index,
                    "operation": "translate_chunk",
                    "status": "error",
                    "error_type": type(exc).__name__,
                },
            )
            return None

        # Success: persist translation, progress, TM, consistency warnings.
        with SessionLocal() as db2:
            db2.execute(
                update(TranslationChunk)
                .where(TranslationChunk.id == chunk_id)
                .values(
                    translation=translation,
                    status="completed",
                    error_message=None,
                    prompt_tokens_used=info.get("prompt_tokens", 0),
                    completion_tokens_used=info.get("completion_tokens", 0),
                    attempts=info.get("attempts", 1),
                )
            )
            db2.execute(
                update(TranslationJob)
                .where(TranslationJob.id == job_id)
                .values(
                    completed_chunks=TranslationJob.completed_chunks + 1,
                    current_chunk_index=index,
                )
            )
            for issue in info.get("consistency_issues", [])[:20]:
                db2.add(
                    ProcessingError(
                        job_id=job_id,
                        document_id=document_id,
                        chunk_id=chunk_id,
                        chunk_index=index,
                        error_type="consistency",
                        severity="warning",
                        message=issue["message"],
                        details=issue.get("expected"),
                    )
                )
            db2.commit()

            if job_settings.get("use_translation_memory", True):
                try:
                    tm = TranslationMemoryService(db2)
                    tm.store(
                        source_text=source_text,
                        target_text=translation,
                        style=job_settings.get("style", "Academic"),
                        domain=job_settings.get("domain", "General"),
                        document_id=document_id,
                        job_id=job_id,
                    )
                except Exception:  # pragma: no cover — TM failure must not break jobs
                    logger.warning(
                        "TM store failed",
                        extra={"operation": "tm_store", "status": "error"},
                    )

        logger.info(
            "Chunk translated",
            extra={
                "job_id": job_id,
                "chunk_index": index,
                "operation": "translate_chunk",
                "status": "success",
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return None

    # ----------------------------------------------------------- assembly
    async def _assemble(self, job_id: str) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            document = db.get(Document, job.document_id)
            chunks = list(
                db.scalars(
                    select(TranslationChunk)
                    .where(TranslationChunk.job_id == job_id)
                    .order_by(TranslationChunk.chunk_index)
                )
            )
            settings_dict = job.settings or {}
            title = (document.title or document.original_filename) if document else "Document"

        self._set_status(job_id, "assembling")

        # ---- Quality control: completeness + terminology consistency ----
        try:
            DocumentAssembler().validate_chunks(chunks)
        except AssemblyError as exc:
            self._set_status(job_id, "failed", error_message=str(exc))
            return

        domains = []
        if settings_dict.get("use_global_dictionary", True):
            domains.append("General")
        if settings_dict.get("use_domain_dictionary", True) and settings_dict.get("domain") not in (
            None,
            "",
            "General",
        ):
            domains.append(settings_dict["domain"])
        if settings_dict.get("use_custom_dictionary", True):
            domains.append("Custom")
        with SessionLocal() as db:
            term_service = TerminologyService(db)
            dictionary_terms = term_service.terms_for_domains(domains) if domains else []
        checker = ConsistencyChecker()
        chunk_results = [
            {"chunk_index": c.chunk_index, "source": c.source_text, "translation": c.translation or ""}
            for c in chunks
        ]
        consistency_report = await asyncio.to_thread(
            checker.aggregate_report, dictionary_terms, chunk_results
        )

        quality_report = {
            "total_chunks": len(chunks),
            "completed_chunks": sum(1 for c in chunks if c.status == "completed"),
            "failed_chunks": sum(1 for c in chunks if c.status == "failed"),
            "empty_translations": sum(1 for c in chunks if not (c.translation or "").strip()),
            "duplicate_indexes": [],
            "missing_indexes": [],
            "terminology": consistency_report,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

        output_name = unique_output_name(title)
        output_path = settings.outputs_dir / f"{job_id}_{output_name}"
        try:
            await asyncio.to_thread(DocumentAssembler().assemble, title, chunks, output_path)
        except AssemblyError as exc:
            self._set_status(job_id, "failed", error_message=str(exc))
            return

        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            job.status = "completed"
            job.progress_percentage = 100.0
            job.quality_report = quality_report
            job.output_filename = f"{job_id}_{output_name}"
            job.completed_at = datetime.now(timezone.utc)
            db.commit()
        logger.info(
            "Job completed",
            extra={"job_id": job_id, "operation": "job", "status": "completed"},
        )

    # ------------------------------------------------------------- helpers
    async def _wait_for_resume(self, handle: JobHandle) -> None:
        await handle.pause_event.wait()
        handle.pause_event.clear()

    @staticmethod
    def _set_status(job_id: str, status: str, error_message: str | None = None) -> None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return
            job.status = status
            if error_message is not None:
                job.error_message = error_message
            elif status in ACTIVE_STATUSES:
                job.error_message = None
            db.commit()

    @staticmethod
    def _friendly(exc: Exception) -> str:
        if isinstance(
            exc, (ProviderNotConfiguredError, AuthenticationError, ProviderError)
        ):
            return exc.user_message
        if isinstance((exc), (AnalysisError, AssemblyError)):
            return str(exc)
        return f"Unexpected error: {type(exc).__name__}."

    # ------------------------------------------------------------- queries
    def get_progress(self, job_id: str) -> dict | None:
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            if job is None:
                return None
            document = db.get(Document, job.document_id)
            current = db.scalars(
                select(TranslationChunk).where(
                    TranslationChunk.job_id == job_id,
                    TranslationChunk.status == "translating",
                )
            ).first()
            recent_errors = list(
                db.scalars(
                    select(ProcessingError)
                    .where(ProcessingError.job_id == job_id)
                    .order_by(ProcessingError.id.desc())
                    .limit(10)
                )
            )
            report = job.quality_report or {}
            return {
                "job_id": job.id,
                "document_id": job.document_id,
                "document_name": document.original_filename if document else None,
                "status": job.status,
                "total_chunks": job.total_chunks,
                "completed_chunks": job.completed_chunks,
                "failed_chunks": job.failed_chunks,
                "current_chunk_index": current.chunk_index if current else job.current_chunk_index,
                "current_chapter": current.chapter if current else None,
                "current_section": current.section if current else None,
                "progress_percentage": job.progress_percentage,
                "eta_seconds": (job.settings or {}).get("eta_seconds"),
                "error_message": job.error_message,
                "recent_errors": [
                    {
                        "chunk_index": e.chunk_index,
                        "type": e.error_type,
                        "severity": e.severity,
                        "message": e.message,
                    }
                    for e in recent_errors
                ],
                "consistency_issues": (
                    report.get("terminology", {}).get("inconsistent_terms", [])
                    if report
                    else []
                ),
            }
