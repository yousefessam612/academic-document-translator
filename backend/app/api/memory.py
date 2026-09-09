"""Translation memory endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.memory import MemoryEntryIn, MemoryEntryOut
from app.services.terminology.memory import TranslationMemoryService

router = APIRouter(prefix="/memory", tags=["translation-memory"])


@router.get("", response_model=list[MemoryEntryOut])
def list_memory(search: str = "", limit: int = 100, offset: int = 0, db: Session = Depends(get_db)):
    service = TranslationMemoryService(db)
    rows, _total = service.list_entries(search, limit, offset)
    return rows


@router.get("/stats")
def memory_stats(db: Session = Depends(get_db)):
    service = TranslationMemoryService(db)
    return service.stats()


@router.post("", response_model=MemoryEntryOut, status_code=201)
def add_memory_entry(payload: MemoryEntryIn, db: Session = Depends(get_db)):
    service = TranslationMemoryService(db)
    entry = service.store(
        source_text=payload.source_text,
        target_text=payload.target_text,
        style=payload.style,
        domain=payload.domain,
    )
    if entry is None:
        raise HTTPException(status_code=400, detail="Could not store entry.")
    return entry


@router.delete("/{entry_id}", status_code=204)
def delete_memory_entry(entry_id: int, db: Session = Depends(get_db)):
    service = TranslationMemoryService(db)
    if not service.delete(entry_id):
        raise HTTPException(status_code=404, detail="Translation memory entry not found.")
    return None
