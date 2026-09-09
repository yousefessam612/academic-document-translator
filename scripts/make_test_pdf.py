"""Create a realistic test PDF (multi-page, headings, paragraphs, table)."""
import sys
from pathlib import Path

import fitz


def build(path_str: str):
    path = Path(path_str)
    doc = fitz.open()
    toc_chapters = []
    for ch in range(1, 4):
        toc_chapters.append(f"Chapter {ch}")
        page = doc.new_page()
        page.insert_text((72, 90), f"Chapter {ch} Visual Impairment Research", fontsize=22)
        page.insert_text((72, 120), f"Section {ch}.1 Introduction", fontsize=15)
        y = 160
        for para in range(6):
            page.insert_text(
                (72, y),
                f"Students with visual impairment and low vision benefit from assistive technology. "
                f"Braille literacy programs improve education outcomes for blind students. "
                f"Chapter {ch} paragraph {para} of the academic research document about visual impairment.",
                fontsize=11,
            )
            y += 34
        if ch == 2:
            # A small table page
            tpage = doc.new_page()
            tpage.insert_text((72, 90), f"Table {ch}.1 Assistive technology overview", fontsize=15)
            rows = [
                ["Device", "Purpose", "Users"],
                ["Screen reader", "Speech output", "Blind students"],
                ["Screen magnifier", "Enlarged display", "Low vision students"],
                ["Braille display", "Tactile output", "Braille readers"],
            ]
            y = 130
            for row in rows:
                x = 72
                for cell in row:
                    tpage.insert_text((x, y), cell, fontsize=11)
                    x += 150
                y += 24
    doc.save(str(path))
    doc.close()
    print(f"Created {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "test_book.pdf")
