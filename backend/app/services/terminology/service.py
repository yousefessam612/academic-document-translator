"""Terminology dictionary service: lookup, CRUD, CSV import/export."""
from __future__ import annotations

import csv
import io
import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.terminology import Terminology
from app.schemas.terminology import TerminologyImportResult

logger = get_logger(__name__)

# Terms longer than this are matched with word boundaries too; short terms
# (acronyms like "AI") always require word boundaries.
_WORD_BOUNDARY_MIN = 4


class TerminologyService:
    def __init__(self, db: Session):
        self.db = db

    # -------------------------------------------------------------- lookups
    def active_terms(self, domains: list[str] | None = None) -> list[Terminology]:
        stmt = select(Terminology).where(Terminology.active.is_(True))
        if domains:
            stmt = stmt.where(Terminology.domain.in_(domains))
        stmt = stmt.order_by(func.length(Terminology.english_term).desc())
        return list(self.db.scalars(stmt))

    def relevant_terms_for_text(self, text: str, domains: list[str] | None = None) -> list[dict]:
        """Return dictionary entries whose English term appears in the text.

        Ordered longest-first so specific terms win over generic ones.
        """
        text_lower = text.lower()
        results: list[dict] = []
        seen: set[str] = set()
        for term in self.active_terms(domains):
            english = term.english_term.strip()
            if not english:
                continue
            key = english.lower()
            if key in seen:
                continue
            eng_lower = english.lower()
            if len(eng_lower) < _WORD_BOUNDARY_MIN:
                found = re.search(rf"\b{re.escape(eng_lower)}\b", text_lower) is not None
            else:
                found = eng_lower in text_lower
            if found:
                seen.add(key)
                results.append(
                    {
                        "id": term.id,
                        "english": english,
                        "arabic": term.arabic_term,
                        "alternatives": list(term.alternatives or []),
                        "domain": term.domain,
                        "priority": term.priority,
                    }
                )
            if len(results) >= 60:  # bound prompt size
                break
        return results

    def terms_for_domains(self, domains: list[str]) -> list[dict]:
        out: list[dict] = []
        for term in self.active_terms(domains):
            out.append(
                {
                    "english": term.english_term,
                    "arabic": term.arabic_term,
                    "alternatives": list(term.alternatives or []),
                    "domain": term.domain,
                }
            )
        return out

    # ----------------------------------------------------------------- CRUD
    def create(self, **kwargs) -> Terminology:
        dup = self._find_duplicate(kwargs["english_term"], kwargs.get("domain", "General"))
        if dup:
            raise ValueError(
                f"'{kwargs['english_term']}' already exists in domain '{dup.domain}'."
            )
        term = Terminology(**kwargs)
        self.db.add(term)
        self.db.commit()
        self.db.refresh(term)
        return term

    def update(self, term_id: int, changes: dict) -> Terminology:
        term = self.db.get(Terminology, term_id)
        if term is None:
            raise LookupError("Terminology entry not found.")
        new_english = changes.get("english_term", term.english_term)
        new_domain = changes.get("domain", term.domain)
        if (new_english, new_domain) != (term.english_term, term.domain):
            dup = self._find_duplicate(new_english, new_domain)
            if dup and dup.id != term.id:
                raise ValueError(f"'{new_english}' already exists in domain '{new_domain}'.")
        for key, value in changes.items():
            if value is not None:
                setattr(term, key, value)
        self.db.commit()
        self.db.refresh(term)
        return term

    def delete(self, term_id: int) -> bool:
        term = self.db.get(Terminology, term_id)
        if term is None:
            return False
        self.db.delete(term)
        self.db.commit()
        return True

    def list(
        self,
        search: str = "",
        domain: str = "",
        active: bool | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> tuple[list[Terminology], int]:
        stmt = select(Terminology)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                Terminology.english_term.ilike(pattern)
                | Terminology.arabic_term.ilike(pattern)
            )
        if domain:
            stmt = stmt.where(Terminology.domain == domain)
        if active is not None:
            stmt = stmt.where(Terminology.active.is_(active))
        total = len(list(self.db.scalars(select(func.count()).select_from(stmt.subquery()))))
        rows = list(
            self.db.scalars(
                stmt.order_by(Terminology.english_term).offset(offset).limit(limit)
            )
        )
        return rows, total

    def domains(self) -> list[str]:
        return sorted({d for (d,) in self.db.execute(select(Terminology.domain).distinct()) if d})

    def _find_duplicate(self, english: str, domain: str) -> Terminology | None:
        stmt = select(Terminology).where(
            func.lower(Terminology.english_term) == english.strip().lower(),
            func.lower(Terminology.domain) == domain.strip().lower(),
        )
        return self.db.scalars(stmt).first()

    # ------------------------------------------------------------ CSV I/O
    def import_csv(self, content: str | bytes) -> TerminologyImportResult:
        """Import terminology from CSV with headers English,Arabic,Domain[,Definition...]."""
        if isinstance(content, bytes):
            for enc in ("utf-8-sig", "utf-8", "cp1256"):
                try:
                    content = content.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            else:
                return TerminologyImportResult(
                    imported=0, updated=0, skipped_duplicates=0,
                    errors=["Could not decode CSV file. Use UTF-8 encoding."],
                )

        reader = csv.reader(io.StringIO(content))
        rows = [r for r in reader if any(c.strip() for c in r)]
        if not rows:
            return TerminologyImportResult(
                imported=0, updated=0, skipped_duplicates=0, errors=["CSV file is empty."]
            )

        header = [c.strip().lower() for c in rows[0]]
        has_header = "english" in header and ("arabic" in header or "arabic_term" in header)
        if has_header:
            idx_en = header.index("english")
            idx_ar = next(i for i, h in enumerate(header) if h in ("arabic", "arabic_term"))
            idx_domain = header.index("domain") if "domain" in header else None
            idx_def = header.index("definition") if "definition" in header else None
            idx_alt = header.index("alternatives") if "alternatives" in header else None
            data_rows = rows[1:]
        else:
            idx_en, idx_ar, idx_domain, idx_def, idx_alt = 0, 1, 2, None, None
            data_rows = rows

        imported = updated = skipped = 0
        errors: list[str] = []
        for line_no, row in enumerate(data_rows, start=2 if has_header else 1):
            if len(row) <= max(idx_en, idx_ar):
                errors.append(f"Row {line_no}: missing English or Arabic column.")
                continue
            english = row[idx_en].strip()
            arabic = row[idx_ar].strip()
            if not english or not arabic:
                errors.append(f"Row {line_no}: empty English or Arabic value.")
                continue
            domain = (row[idx_domain].strip() if idx_domain is not None and len(row) > idx_domain else "") or "General"
            definition = row[idx_def].strip() if idx_def is not None and len(row) > idx_def else ""
            alternatives = (
                [a.strip() for a in row[idx_alt].split(";") if a.strip()]
                if idx_alt is not None and len(row) > idx_alt and row[idx_alt].strip()
                else []
            )
            existing = self._find_duplicate(english, domain)
            if existing:
                skipped += 1
                continue
            self.db.add(
                Terminology(
                    english_term=english,
                    arabic_term=arabic,
                    domain=domain,
                    definition=definition,
                    alternatives=alternatives,
                )
            )
            imported += 1
        self.db.commit()
        logger.info(
            "Terminology CSV import finished",
            extra={
                "operation": "terminology_import",
                "status": "success",
                "imported": imported,
                "skipped": skipped,
                "errors": len(errors),
            },
        )
        return TerminologyImportResult(
            imported=imported, updated=updated, skipped_duplicates=skipped, errors=errors[:50]
        )

    def export_csv(self) -> str:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["English", "Arabic", "Domain", "Definition", "Alternatives"])
        for term in self.db.scalars(select(Terminology).order_by(Terminology.english_term)):
            writer.writerow(
                [
                    term.english_term,
                    term.arabic_term,
                    term.domain,
                    term.definition or "",
                    ";".join(term.alternatives or []),
                ]
            )
        return out.getvalue()
