"""Terminology service + CSV import tests."""
from __future__ import annotations

import pytest

from app.services.terminology.seed import seed_default_terminology
from app.services.terminology.service import TerminologyService


class TestTerminologyCRUD:
    def test_create_and_lookup(self, db_session):
        service = TerminologyService(db_session)
        service.create(
            english_term="Visual impairment",
            arabic_term="الإعاقة البصرية",
            domain="Visual Impairment",
            alternatives=["الضعف البصري"],
        )
        terms = service.relevant_terms_for_text(
            "Children with visual impairment benefit from early intervention.",
            ["Visual Impairment"],
        )
        assert any(t["english"] == "Visual impairment" for t in terms)

    def test_duplicate_prevented(self, db_session):
        service = TerminologyService(db_session)
        service.create(english_term="Low vision", arabic_term="ضعف البصر", domain="Visual Impairment")
        with pytest.raises(ValueError):
            service.create(english_term="low vision", arabic_term="آخر", domain="Visual Impairment")
        # Same term in a different domain is allowed
        service.create(english_term="Low vision", arabic_term="ضعف البصر", domain="General")

    def test_update_and_delete(self, db_session):
        service = TerminologyService(db_session)
        term = service.create(english_term="Blindness", arabic_term="العمى", domain="General")
        updated = service.update(term.id, {"arabic_term": "فقدان البصر"})
        assert updated.arabic_term == "فقدان البصر"
        assert service.delete(term.id) is True
        rows, _ = service.list()
        assert all(r.english_term != "Blindness" for r in rows)

    def test_inactive_terms_excluded(self, db_session):
        service = TerminologyService(db_session)
        term = service.create(english_term="Cortical visual impairment", arabic_term="الإعاقة البصرية القشرية", domain="Visual Impairment")
        service.update(term.id, {"active": False})
        terms = service.relevant_terms_for_text("Cortical visual impairment is a condition.", ["Visual Impairment"])
        assert not any(t["english"] == "Cortical visual impairment" for t in terms)

    def test_word_boundary_short_terms(self, db_session):
        service = TerminologyService(db_session)
        service.create(english_term="AI", arabic_term="الذكاء الاصطناعي", domain="General")
        # "AI" inside a word like "AIM" must not match
        terms = service.relevant_terms_for_text("The AIMS score was calculated.", ["General"])
        assert not any(t["english"] == "AI" for t in terms)
        terms = service.relevant_terms_for_text("AI improves education.", ["General"])
        assert any(t["english"] == "AI" for t in terms)


class TestCSVImport:
    def test_import_with_headers(self, db_session):
        service = TerminologyService(db_session)
        csv_content = (
            "English,Arabic,Domain\n"
            "Visual impairment,الإعاقة البصرية,Visual Impairment\n"
            "Low vision,ضعف البصر,Visual Impairment\n"
        )
        result = service.import_csv(csv_content)
        assert result.imported == 2
        assert result.errors == []

    def test_import_prevents_duplicates(self, db_session):
        service = TerminologyService(db_session)
        csv_content = "English,Arabic,Domain\nVisual impairment,الإعاقة البصرية,Visual Impairment\n"
        first = service.import_csv(csv_content)
        second = service.import_csv(csv_content)
        assert first.imported == 1
        assert second.imported == 0
        assert second.skipped_duplicates == 1

    def test_import_validation_errors(self, db_session):
        service = TerminologyService(db_session)
        csv_content = (
            "English,Arabic,Domain\n"
            "OnlyEnglish\n"
            ",القيمة العربية,General\n"
            "Valid Term,مصطلح صحيح,General\n"
        )
        result = service.import_csv(csv_content)
        assert result.imported == 1
        assert len(result.errors) == 2

    def test_import_without_headers(self, db_session):
        service = TerminologyService(db_session)
        csv_content = "Orientation and mobility,التوجه والحركة,Visual Impairment\n"
        result = service.import_csv(csv_content)
        assert result.imported == 1

    def test_export_roundtrip(self, db_session):
        service = TerminologyService(db_session)
        service.import_csv("English,Arabic,Domain\nBraille,برايل,Visual Impairment\n")
        exported = service.export_csv()
        assert "Braille" in exported and "برايل" in exported
        result = service.import_csv(exported.encode("utf-8"))
        assert result.skipped_duplicates >= 1


class TestSeed:
    def test_seed_idempotent(self, db_session):
        assert seed_default_terminology(db_session) > 0
        assert seed_default_terminology(db_session) == 0
        service = TerminologyService(db_session)
        terms = service.relevant_terms_for_text(
            "Expanded Core Curriculum covers braille literacy.", ["Special Education", "Visual Impairment"]
        )
        assert any(t["english"] == "Expanded Core Curriculum" for t in terms)
        assert any(t["english"] == "Braille literacy" for t in terms)
