"""Document endpoints: upload (100 MB streaming), list, analyze, download, delete."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import (
    UnsafeFilenameError,
    sanitize_filename,
    validate_extension,
)
from app.db.database import get_db
from app.models.document import Document
from app.models.job import TranslationJob
from app.models.chunk import TranslationChunk
from app.schemas.document import DocumentListOut, DocumentOut
from app.utils import files as file_utils

logger = get_logger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Streamed upload with validation. Never trusts the client filename."""
    raw_name = file.filename or "upload"
    try:
        display_name = sanitize_filename(raw_name)
        extension = validate_extension(display_name)
    except UnsafeFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Cheap early check on Content-Length when the client provides it.
    declared = file.size
    if declared is not None and declared > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_file_size_mb} MB limit.",
        )

    try:
        stored_name, size = await file_utils.save_upload_streaming(file, extension)
    except file_utils.FileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsafeFilenameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail="Failed to store the uploaded file.") from exc
    finally:
        await file.close()

    stored_path = settings.uploads_dir / stored_name
    try:
        file_utils.verify_type(stored_path, extension)
    except UnsafeFilenameError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    import uuid

    document = Document(
        id=uuid.uuid4().hex,
        original_filename=display_name,
        stored_filename=stored_name,
        file_type=extension.lstrip("."),
        mime_type=file.content_type or "",
        file_size=size,
        status="uploaded",
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    # Automatic analysis right after upload (spec: analyze after upload).
    from app.services.document.analysis_runner import spawn_analysis

    spawn_analysis(document.id)
    logger.info(
        "Document uploaded",
        extra={
            "document_id": document.id,
            "operation": "upload",
            "status": "success",
            "size": size,
        },
    )
    return document


@router.get("", response_model=DocumentListOut)
def list_documents(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Document).order_by(Document.created_at.desc())
    docs = list(db.scalars(stmt.offset(offset).limit(min(limit, 200))))
    total = len(list(db.scalars(select(Document.id))))
    return DocumentListOut(documents=[DocumentOut.model_validate(d) for d in docs], total=total)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.post("/{document_id}/analyze")
async def analyze_document(document_id: str, db: Session = Depends(get_db)):
    """(Re-)analyze a document in the background."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    from app.services.document.analysis_runner import is_running, spawn_analysis

    if is_running(document_id):
        raise HTTPException(status_code=409, detail="Analysis is already running for this document.")
    spawn_analysis(document_id)
    return {"message": "Analysis started."}


@router.get("/{document_id}/structure")
def get_document_structure(document_id: str, limit: int = 500, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    structure = (document.structure or [])[:limit]
    return {"total_blocks": len(document.structure or []), "blocks": structure}


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """User-initiated delete: removes DB rows and stored files."""
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    upload_path = settings.uploads_dir / document.stored_filename
    upload_path.unlink(missing_ok=True)  # original is only removed on explicit request
    jobs = list(db.scalars(select(TranslationJob).where(TranslationJob.document_id == document_id)))
    for job in jobs:
        if job.output_filename:
            (settings.outputs_dir / job.output_filename).unlink(missing_ok=True)
    db.delete(document)  # cascades to chunks/jobs rows
    db.commit()
    return None


@router.get("/{document_id}/download/original")
def download_original(document_id: str, db: Session = Depends(get_db)):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = settings.uploads_dir / document.stored_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Original file not found in storage.")
    return FileResponse(
        path,
        filename=document.original_filename,
        media_type="application/octet-stream",
    )


@router.get("/{document_id}/download/translated")
def download_translated(document_id: str, db: Session = Depends(get_db)):
    """Download the generated Arabic DOCX (latest completed job)."""
    job = db.scalars(
        select(TranslationJob)
        .where(
            TranslationJob.document_id == document_id,
            TranslationJob.status == "completed",
        )
        .order_by(TranslationJob.completed_at.desc())
    ).first()
    if job is None or not job.output_filename:
        raise HTTPException(
            status_code=404,
            detail="No completed translation for this document yet.",
        )
    path = settings.outputs_dir / job.output_filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Translated file not found in storage.")
    return FileResponse(
        path,
        filename=job.output_filename.split("_", 1)[-1],
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
