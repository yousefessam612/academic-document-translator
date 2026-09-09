"""Terminology dictionary endpoints: CRUD + CSV import/export."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.terminology import (
    TerminologyImportResult,
    TerminologyIn,
    TerminologyOut,
    TerminologyUpdateIn,
)
from app.services.terminology.service import TerminologyService

router = APIRouter(prefix="/terminology", tags=["terminology"])


@router.get("", response_model=list[TerminologyOut])
def list_terms(
    search: str = "",
    domain: str = "",
    active: bool | None = None,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    service = TerminologyService(db)
    rows, _total = service.list(search, domain, active, limit, offset)
    return rows


@router.get("/meta")
def terminology_meta(db: Session = Depends(get_db)):
    service = TerminologyService(db)
    return {"domains": service.domains()}


@router.post("", response_model=TerminologyOut, status_code=201)
def create_term(payload: TerminologyIn, db: Session = Depends(get_db)):
    service = TerminologyService(db)
    try:
        return service.create(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.put("/{term_id}", response_model=TerminologyOut)
def update_term(term_id: int, payload: TerminologyUpdateIn, db: Session = Depends(get_db)):
    service = TerminologyService(db)
    try:
        return service.update(term_id, payload.model_dump(exclude_none=True))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{term_id}", status_code=204)
def delete_term(term_id: int, db: Session = Depends(get_db)):
    service = TerminologyService(db)
    if not service.delete(term_id):
        raise HTTPException(status_code=404, detail="Terminology entry not found.")
    return None


@router.post("/import", response_model=TerminologyImportResult)
async def import_terms(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Import a CSV terminology file (headers: English,Arabic,Domain[,Definition,Alternatives])."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file (.csv).")
    content = await file.read()
    await file.close()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Terminology file exceeds 10 MB.")
    service = TerminologyService(db)
    result = service.import_csv(content)
    return result


@router.get("/export", response_class=PlainTextResponse)
def export_terms(db: Session = Depends(get_db)):
    service = TerminologyService(db)
    return service.export_csv()
