"""Translation memory: exact + fuzzy retrieval, safe storage.

Similarity is currently difflib-based (lightweight, local, no extra
services); the interface is designed so an embeddings backend can replace it.
Matches are provided to the LLM as context — never auto-replaced.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.memory import TranslationMemoryEntry
from app.utils.text import hash_text, normalize_for_hash

FUZZY_THRESHOLD = 0.72
FUZZY_SCAN_LIMIT = 400  # candidate rows scanned per lookup (recent first)


class TranslationMemoryService:
    def __init__(self, db: Session):
        self.db = db

    def lookup(self, source_text: str, target_language: str = "ar") -> list[dict]:
        """Exact match first, then fuzzy matches, best-first."""
        exact_hash = hash_text(source_text)
        exact = self.db.scalars(
            select(TranslationMemoryEntry).where(
                TranslationMemoryEntry.source_hash == exact_hash,
                TranslationMemoryEntry.target_language == target_language,
                TranslationMemoryEntry.approved.is_(True),
            )
        ).first()
        if exact:
            return [
                {
                    "source": exact.source_text,
                    "target": exact.target_text,
                    "similarity": 1.0,
                    "exact": True,
                }
            ]

        candidates = list(
            self.db.scalars(
                select(TranslationMemoryEntry)
                .where(
                    TranslationMemoryEntry.target_language == target_language,
                    TranslationMemoryEntry.approved.is_(True),
                )
                .order_by(TranslationMemoryEntry.id.desc())
                .limit(FUZZY_SCAN_LIMIT)
            )
        )
        norm_source = normalize_for_hash(source_text)
        scored: list[tuple[float, TranslationMemoryEntry]] = []
        for cand in candidates:
            ratio = SequenceMatcher(
                None, norm_source, normalize_for_hash(cand.source_text)
            ).quick_ratio()
            if ratio >= FUZZY_THRESHOLD:
                real = SequenceMatcher(
                    None, norm_source, normalize_for_hash(cand.source_text)
                ).ratio()
                if real >= FUZZY_THRESHOLD:
                    scored.append((real, cand))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            {
                "source": c.source_text,
                "target": c.target_text,
                "similarity": round(r, 2),
                "exact": False,
            }
            for r, c in scored[:3]
        ]

    def store(
        self,
        source_text: str,
        target_text: str,
        target_language: str = "ar",
        style: str = "Academic",
        domain: str = "General",
        document_id: str | None = None,
        job_id: str | None = None,
    ) -> TranslationMemoryEntry | None:
        """Store an approved source/translation pair (deduplicated by hash)."""
        source_text = source_text.strip()
        target_text = target_text.strip()
        if not source_text or not target_text:
            return None
        source_hash = hash_text(source_text)
        existing = self.db.scalars(
            select(TranslationMemoryEntry).where(
                TranslationMemoryEntry.source_hash == source_hash,
                TranslationMemoryEntry.target_language == target_language,
            )
        ).first()
        if existing:
            existing.use_count += 1
            self.db.commit()
            return existing
        entry = TranslationMemoryEntry(
            source_hash=source_hash,
            source_text=source_text,
            target_text=target_text,
            target_language=target_language,
            style=style,
            domain=domain,
            document_id=document_id,
            job_id=job_id,
        )
        self.db.add(entry)
        self.db.commit()
        return entry

    def list_entries(self, search: str = "", limit: int = 100, offset: int = 0):
        stmt = select(TranslationMemoryEntry)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                TranslationMemoryEntry.source_text.ilike(pattern)
                | TranslationMemoryEntry.target_text.ilike(pattern)
            )
        total = self.db.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = list(
            self.db.scalars(
                stmt.order_by(TranslationMemoryEntry.id.desc()).offset(offset).limit(limit)
            )
        )
        return rows, total or 0

    def delete(self, entry_id: int) -> bool:
        entry = self.db.get(TranslationMemoryEntry, entry_id)
        if entry is None:
            return False
        self.db.delete(entry)
        self.db.commit()
        return True

    def create_manual(self, **kwargs) -> TranslationMemoryEntry:
        return self.store(**kwargs) or TranslationMemoryEntry(
            source_text=kwargs["source_text"], target_text=kwargs["target_text"]
        )

    def stats(self) -> dict:
        total = self.db.scalar(select(func.count(TranslationMemoryEntry.id))) or 0
        return {"total_entries": total}
