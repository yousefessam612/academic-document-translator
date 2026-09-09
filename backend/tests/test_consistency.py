"""Terminology consistency checker tests."""
from __future__ import annotations

from app.services.translation.consistency import ConsistencyChecker


TERMS = [
    {"english": "Visual impairment", "arabic": "الإعاقة البصرية", "alternatives": ["القصور البصري"]},
    {"english": "Low vision", "arabic": "ضعف البصر", "alternatives": []},
]


class TestChunkCheck:
    def test_preferred_used_no_issue(self):
        checker = ConsistencyChecker()
        issues = checker.check_chunk(
            "Visual impairment affects children.",
            "تؤثر الإعاقة البصرية على الأطفال.",
            1,
            TERMS,
        )
        assert issues == []

    def test_alternative_used_flagged(self):
        checker = ConsistencyChecker()
        issues = checker.check_chunk(
            "Visual impairment affects children.",
            "يؤثر القصور البصري على الأطفال.",
            2,
            TERMS,
        )
        assert len(issues) == 1
        assert issues[0]["type"] == "alternative_used"
        assert "Chunk 2" in issues[0]["message"]

    def test_unknown_translation_flagged(self):
        checker = ConsistencyChecker()
        issues = checker.check_chunk(
            "Visual impairment affects children.",
            "تؤثر مشكلة البصر على الأطفال.",
            3,
            TERMS,
        )
        assert len(issues) == 1
        assert issues[0]["type"] == "preferred_missing"

    def test_term_not_in_source_ignored(self):
        checker = ConsistencyChecker()
        issues = checker.check_chunk(
            "Unrelated text about mathematics.",
            "نص غير ذي صلة عن الرياضيات.",
            4,
            TERMS,
        )
        assert issues == []


class TestAggregateReport:
    def test_inconsistent_term_detected(self):
        checker = ConsistencyChecker()
        chunks = [
            {"chunk_index": 1, "source": "Visual impairment research.", "translation": "بحث الإعاقة البصرية."},
            {"chunk_index": 47, "source": "Visual impairment research.", "translation": "بحث ضعف الإعاقة البصرية."},
            {"chunk_index": 82, "source": "Visual impairment research.", "translation": "بحث القصور البصري."},
        ]
        report = checker.aggregate_report(TERMS, chunks)
        inconsistent = {t["english"]: t for t in report["inconsistent_terms"]}
        assert "Visual impairment" in inconsistent
        used = inconsistent["Visual impairment"]["used"]
        # Chunks 1 and 47 contain the preferred translation
        assert 1 in used.get("الإعاقة البصرية", [])
        assert 47 in used.get("الإعاقة البصرية", [])
        # Chunk 82 used the registered alternative
        assert 82 in used.get("alt: القصور البصري", [])

    def test_consistent_terms_reported(self):
        checker = ConsistencyChecker()
        chunks = [
            {"chunk_index": 1, "source": "Low vision tools.", "translation": "أدوات ضعف البصر."},
            {"chunk_index": 2, "source": "Low vision tools.", "translation": "أدوات ضعف البصر."},
        ]
        report = checker.aggregate_report(TERMS, chunks)
        assert report["consistent_terms"] >= 1
        assert all(t["english"] != "Low vision" for t in report["inconsistent_terms"])

    def test_uniformly_missing_preferred_not_flagged_as_inconsistent(self):
        checker = ConsistencyChecker()
        chunks = [
            {"chunk_index": 1, "source": "Visual impairment text.", "translation": "نص آخر تماماً."},
            {"chunk_index": 2, "source": "Visual impairment text.", "translation": "نص ثالث تماماً."},
        ]
        report = checker.aggregate_report(TERMS, chunks)
        # Uniform non-preferred usage is not 'inconsistent' (single variant)
        assert all(t["english"] != "Visual impairment" for t in report["inconsistent_terms"])
