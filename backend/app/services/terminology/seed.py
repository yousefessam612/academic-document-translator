"""Seed dictionary with core academic/special-education terminology."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.terminology import Terminology

DEFAULT_TERMS: list[dict] = [
    {"english_term": "Visual impairment", "arabic_term": "الإعاقة البصرية", "domain": "Visual Impairment"},
    {"english_term": "Low vision", "arabic_term": "ضعف البصر", "domain": "Visual Impairment"},
    {"english_term": "Blindness", "arabic_term": "العمى", "domain": "Visual Impairment"},
    {"english_term": "Assistive technology", "arabic_term": "التكنولوجيا المساعدة", "domain": "Assistive Technology"},
    {"english_term": "Orientation and mobility", "arabic_term": "التوجه والحركة", "domain": "Visual Impairment"},
    {"english_term": "Braille literacy", "arabic_term": "محو أمية برايل", "domain": "Visual Impairment"},
    {"english_term": "Braille", "arabic_term": "برايل", "domain": "Visual Impairment"},
    {"english_term": "Expanded Core Curriculum", "arabic_term": "المنهج الموسع للمهارات الأساسية", "domain": "Special Education"},
    {"english_term": "Special education", "arabic_term": "التربية الخاصة", "domain": "Special Education"},
    {"english_term": "Inclusive education", "arabic_term": "التعليم الدامج", "domain": "Education"},
    {"english_term": "Individualized Education Program", "arabic_term": "الخطة التعليمية الفردية", "domain": "Special Education"},
    {"english_term": "Early intervention", "arabic_term": "التدخل المبكر", "domain": "Special Education"},
    {"english_term": "Cerebral palsy", "arabic_term": "الشلل الدماغي", "domain": "Special Education"},
    {"english_term": "Hearing impairment", "arabic_term": "الإعاقة السمعية", "domain": "Special Education"},
    {"english_term": "Intellectual disability", "arabic_term": "الإعاقة الذهنية", "domain": "Special Education"},
    {"english_term": "Learning disability", "arabic_term": "صعوبات التعلم", "domain": "Special Education"},
    {"english_term": "Screen reader", "arabic_term": "قارئ الشاشة", "domain": "Assistive Technology"},
    {"english_term": "Screen magnifier", "arabic_term": "مكبر الشاشة", "domain": "Assistive Technology"},
    {"english_term": "Tactile graphics", "arabic_term": "الرسوم اللمسية", "domain": "Visual Impairment"},
    {"english_term": "Congenital", "arabic_term": "خلقي", "domain": "General"},
    {"english_term": "Ophthalmologist", "arabic_term": "طبيب العيون", "domain": "Visual Impairment"},
    {"english_term": "Optometrist", "arabic_term": "أخصائي البصريات", "domain": "Visual Impairment"},
    {"english_term": "Visual acuity", "arabic_term": "حدة البصر", "domain": "Visual Impairment"},
    {"english_term": "Visual field", "arabic_term": "المجال البصري", "domain": "Visual Impairment"},
    {"english_term": "Cognitive", "arabic_term": "معرفي", "domain": "Psychology"},
    {"english_term": "Metacognition", "arabic_term": "ما وراء المعرفة", "domain": "Psychology"},
    {"english_term": "Working memory", "arabic_term": "ذاكرة العمل", "domain": "Psychology"},
    {"english_term": "Case study", "arabic_term": "دراسة حالة", "domain": "General"},
    {"english_term": "Peer-reviewed", "arabic_term": "محكم علمياً", "domain": "General"},
    {"english_term": "Abstract", "arabic_term": "المستخلص", "domain": "General"},
]


def seed_default_terminology(db: Session) -> int:
    """Insert default terms once; returns number inserted."""
    count = 0
    existing = {
        (t.english_term.lower(), t.domain.lower())
        for t in db.scalars(select(Terminology))
    }
    for term in DEFAULT_TERMS:
        key = (term["english_term"].lower(), term["domain"].lower())
        if key in existing:
            continue
        db.add(Terminology(**term))
        existing.add(key)
        count += 1
    if count:
        db.commit()
    return count
