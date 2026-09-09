"""Background document analysis.

Runs analysis automatically after upload (and on demand), updating
Document.status live: analyzing -> (ocr) -> analyzed | analysis_failed.
"""
from __future__ import annotations

import asyncio

from app.core.config import settings
from app.core.logging_config import get_logger
from app.db.database import SessionLocal
from app.models.document import Document
from app.services.document.analyzer import AnalysisError, DocumentAnalyzer

logger = get_logger(__name__)

# document ids with a live analysis task (prevents duplicate runs)
_running: set[str] = set()


def is_running(document_id: str) -> bool:
    return document_id in _running


def _set_doc_status(document_id: str, status: str, analysis: dict | None = None) -> None:
    with SessionLocal() as db:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = status
        if analysis is not None:
            doc.analysis = analysis
        db.commit()


async def run_analysis(document_id: str, use_ocr: bool = True) -> None:
    if document_id in _running:
        return
    _running.add(document_id)
    logger.info(
        "Document analysis started",
        extra={"document_id": document_id, "operation": "analyze", "status": "started"},
    )
    try:
        with SessionLocal() as db:
            doc = db.get(Document, document_id)
            if doc is None:
                return
            stored = doc.stored_filename
            file_type = doc.file_type
            original = doc.original_filename

        upload_path = settings.uploads_dir / stored
        if not upload_path.exists():
            _set_doc_status(
                document_id, "analysis_failed", {"error": "The uploaded file is missing from storage."}
            )
            return

        _set_doc_status(document_id, "analyzing")

        def progress(status: str) -> None:
            # Map analyzer progress to document statuses the UI understands.
            if status.startswith("ocr"):
                parts = status.split(" ", 1)
                payload = {"ocr_progress": parts[1]} if len(parts) == 2 else {}
                _set_doc_status(document_id, "ocr", payload)
            elif status == "extracting":
                _set_doc_status(document_id, "extracting")

        try:
            analysis = await asyncio.to_thread(
                DocumentAnalyzer().analyze,
                upload_path,
                file_type,
                original,
                progress,
                use_ocr,
            )
        except AnalysisError as exc:
            logger.warning(
                "Document analysis failed",
                extra={
                    "document_id": document_id,
                    "operation": "analyze",
                    "status": "error",
                    "error_type": "analysis",
                },
            )
            _set_doc_status(document_id, "analysis_failed", {"error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Document analysis crashed",
                extra={
                    "document_id": document_id,
                    "operation": "analyze",
                    "status": "error",
                    "error_type": type(exc).__name__,
                },
            )
            _set_doc_status(
                document_id,
                "analysis_failed",
                {"error": f"Analysis failed unexpectedly: {type(exc).__name__}."},
            )
            return

        structure = analysis.pop("structure", [])
        with SessionLocal() as db:
            doc = db.get(Document, document_id)
            if doc is None:
                return
            doc.structure = structure
            doc.title = analysis.get("title", "")
            doc.analysis = analysis
            doc.requires_ocr = analysis.get("is_scanned", False)
            doc.status = "analyzed"
            db.commit()
        logger.info(
            "Document analysis completed",
            extra={
                "document_id": document_id,
                "operation": "analyze",
                "status": "success",
                "chunks": analysis.get("estimated_chunks"),
            },
        )
    finally:
        _running.discard(document_id)


def spawn_analysis(document_id: str, use_ocr: bool = True) -> bool:
    """Start analysis in the background. Returns False if already running."""
    if document_id in _running:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(run_analysis(document_id, use_ocr))
        return True
    loop.create_task(run_analysis(document_id, use_ocr))
    return True
