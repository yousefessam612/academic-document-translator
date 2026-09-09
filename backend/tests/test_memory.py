"""Translation memory tests: exact/fuzzy lookup, dedup, similarity."""
from __future__ import annotations

from app.services.terminology.memory import TranslationMemoryService


class TestTranslationMemory:
    def test_store_and_exact_lookup(self, db_session):
        tm = TranslationMemoryService(db_session)
        tm.store(
            source_text="Students with visual impairment need assistive technology.",
            target_text="يحتاج الطلاب ذوو الإعاقة البصرية إلى التكنولوجيا المساعدة.",
        )
        matches = tm.lookup("Students with visual impairment need assistive technology.")
        assert len(matches) == 1
        assert matches[0]["exact"] is True
        assert "التكنولوجيا المساعدة" in matches[0]["target"]

    def test_exact_lookup_ignores_whitespace_case(self, db_session):
        tm = TranslationMemoryService(db_session)
        tm.store(source_text="Low vision  affects reading.", target_text="ضعف البصر يؤثر على القراءة.")
        matches = tm.lookup("low vision affects  reading.")
        assert len(matches) == 1
        assert matches[0]["exact"] is True

    def test_fuzzy_lookup(self, db_session):
        tm = TranslationMemoryService(db_session)
        tm.store(
            source_text="The study examined children with low vision in inclusive classrooms.",
            target_text="فحصت الدراسة الأطفال ذوي ضعف البصر في الفصول الدامجة.",
        )
        matches = tm.lookup("The study examined children with low vision in inclusive schools.")
        assert matches, "similar segment should produce a fuzzy match"
        assert matches[0]["similarity"] >= 0.7
        assert matches[0]["exact"] is False

    def test_no_match_for_unrelated(self, db_session):
        tm = TranslationMemoryService(db_session)
        tm.store(source_text="Quantum computing basics", target_text="أساسيات الحوسبة الكمية")
        assert tm.lookup("The history of ancient Rome and its emperors.") == []

    def test_dedup_on_store(self, db_session):
        tm = TranslationMemoryService(db_session)
        tm.store(source_text="Same source", target_text="نفس المصدر")
        tm.store(source_text="Same source", target_text="نفس المصدر")
        rows, total = tm.list_entries()
        assert total == 1
        assert rows[0].use_count == 1

    def test_delete(self, db_session):
        tm = TranslationMemoryService(db_session)
        entry = tm.store(source_text="ToDelete", target_text="للحذف")
        assert tm.delete(entry.id) is True
        assert tm.lookup("ToDelete") == []
