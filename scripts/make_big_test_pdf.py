"""Create a substantial test book: 20 pages, 10,000+ words of realistic
academic content about visual impairment education."""
import sys
import textwrap
from pathlib import Path

import fitz

CHAPTERS = [
    ("Understanding Visual Impairment in Educational Contexts",
     "visual impairment", "low vision", "blindness"),
    ("Assistive Technology for Learners with Visual Impairment",
     "assistive technology", "screen reader", "braille display"),
    ("Braille Literacy and the Expanded Core Curriculum",
     "braille literacy", "expanded core curriculum", "orientation and mobility"),
    ("Inclusive Education and Classroom Practice",
     "inclusive education", "individualized education program", "early intervention"),
    ("Assessment, Family Engagement, and Future Directions",
     "special education", "individualized education program", "early intervention"),
]

SENTENCE_TEMPLATES = [
    "Students with {t1} require systematic assessment to determine appropriate educational interventions and support services.",
    "Research on {t2} demonstrates that early identification significantly improves long-term academic and developmental outcomes.",
    "Teachers who work with {t1} must understand both the medical and educational implications of each diagnosis.",
    "The use of {t3} in the classroom has expanded considerably over the past two decades, changing instructional practices.",
    "Families of children with {t2} often report needing more guidance about available community resources and support networks.",
    "Effective instruction for learners with {t1} combines specialized techniques with evidence-based general pedagogy.",
    "Studies of {t3} adoption show that ongoing professional development is essential for sustained implementation quality.",
    "Collaboration between general educators and specialists remains a cornerstone of successful {t2} programming.",
    "Data collected across multiple school districts indicate that {t1} affects roughly one in a thousand enrolled students.",
    "The development of {t3} skills should begin as early as possible and continue throughout the student's academic career.",
    "Curriculum designers must consider the needs of students with {t2} when creating accessible learning materials.",
    "Longitudinal studies of {t1} emphasize the importance of self-advocacy skills in post-school transitions.",
    "Classroom teachers who receive training in {t3} report greater confidence and better instructional outcomes.",
    "The literature on {t2} continues to grow, reflecting increased scholarly attention to educational equity.",
    "Assessment teams evaluating {t1} should include professionals from multiple disciplines to capture the full picture.",
    "Assistive technology such as {t3} enables students to access the general curriculum alongside their peers.",
    "Policy frameworks governing {t2} vary considerably between jurisdictions, affecting service delivery models.",
    "Parent involvement programs linked to {t1} services show measurable benefits for both children and caregivers.",
    "Inclusive placements for students with {t2} require careful planning, adequate resources, and committed leadership.",
    "The field of {t3} has benefited from partnerships between universities, schools, and advocacy organizations.",
]


def _write_wrapped(page, x: float, y: float, text: str, fontsize: float = 10) -> float:
    """Write text word-wrapped to page width; returns the next y position."""
    chars = 108  # ~ usable chars per line at 10pt in a 612pt-wide page
    for line in textwrap.wrap(text, width=chars) or [""]:
        page.insert_text((x, y), line, fontsize=fontsize)
        y += 14
    return y


def build(path_str: str, pages: int = 25, words_target: int = 10200):
    path = Path(path_str)
    rng = __import__("random").Random(42)
    doc = fitz.open()
    words = 0
    chapter_pages = pages // len(CHAPTERS)

    for ci, (title, t1, t2, t3) in enumerate(CHAPTERS, start=1):
        page = doc.new_page()
        page.insert_text((72, 96), f"Chapter {ci}", fontsize=24)
        page.insert_text((72, 132), title, fontsize=18)
        words += len(f"Chapter {ci} {title}".split())
        y = 176
        for template in SENTENCE_TEMPLATES:
            text = template.format(t1=t1, t2=t2, t3=t3)
            body = text + " " + text
            y = _write_wrapped(page, 72, y, body)
            words += len(body.split())
            if y > 720:
                break
        # additional pages per chapter
        for extra in range(1, chapter_pages):
            p = doc.new_page()
            p.insert_text((72, 72), f"Chapter {ci} (continued)", fontsize=14)
            words += 3
            y = 108
            while y < 720:
                template = rng.choice(SENTENCE_TEMPLATES)
                text = template.format(t1=t1, t2=t2, t3=t3)
                body = text + " " + rng.choice(SENTENCE_TEMPLATES).format(t1=t1, t2=t2, t3=t3)
                y = _write_wrapped(p, 72, y, body)
                words += len(body.split())

    doc.save(str(path))
    doc.close()
    print(f"Created {path}: {pages} pages, ~{words} words written, {path.stat().st_size} bytes")

    # Verify the EXTRACTED text really carries 10k+ words (nothing clipped).
    check = fitz.open(str(path))
    assert len(check) == pages
    extracted_words = len(check[0:pages].get_text().split()) if False else sum(
        len(page.get_text().split()) for page in check
    )
    check.close()
    print(f"Extracted from PDF: {extracted_words} words across {pages} pages")
    assert extracted_words >= words_target, f"only {extracted_words} words extracted"


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "big_test_book.pdf")
