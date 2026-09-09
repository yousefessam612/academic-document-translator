"""Plain-text extraction with light heading/paragraph structure detection."""
from __future__ import annotations

import re
from pathlib import Path

from app.services.document.structure import Block, HEADING, LIST_ITEM, PARAGRAPH

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+)$")
_CHAPTER_RE = re.compile(r"^(chapter|part)\s+[\dIVXLC]+", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*•‣▪]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*(\d{1,2})[.)]\s+(.*)$")

_ENCODINGS = ("utf-8-sig", "utf-8", "cp1256", "cp1252", "latin-1")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def extract_txt_blocks(path: Path) -> tuple[list[Block], dict]:
    text = _read_text(path)
    blocks: list[Block] = []
    seq = 0
    total_chars = 0

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for para in paragraphs:
        lines = para.splitlines()
        # Markdown or obvious heading?
        first = lines[0].strip() if lines else ""
        md = _MD_HEADING.match(first)
        if md and len(lines) == 1:
            blocks.append(
                Block(seq=seq, type=HEADING, text=md.group(2).strip(), level=len(md.group(1)))
            )
            seq += 1
            continue
        if (
            len(lines) == 1
            and len(first) <= 100
            and first.endswith((".", ":", "؟"))
            is False
            and (_CHAPTER_RE.match(first) or first.isupper())
            and any(c.isalpha() for c in first)
        ):
            blocks.append(
                Block(
                    seq=seq,
                    type=HEADING,
                    text=first,
                    level=1 if _CHAPTER_RE.match(first) else 2,
                )
            )
            seq += 1
            continue

        # Bullet/numbered list block
        if all(_BULLET_RE.match(l) or _NUMBERED_RE.match(l) for l in lines if l.strip()):
            for line in lines:
                b = _BULLET_RE.match(line)
                n = _NUMBERED_RE.match(line)
                if b:
                    blocks.append(Block(seq=seq, type=LIST_ITEM, text=b.group(1).strip(), marker="•"))
                    seq += 1
                elif n:
                    blocks.append(
                        Block(seq=seq, type=LIST_ITEM, text=n.group(2).strip(), marker=f"{n.group(1)}.")
                    )
                    seq += 1
            continue

        blocks.append(Block(seq=seq, type=PARAGRAPH, text=" ".join(l.strip() for l in lines)))
        seq += 1

    total_chars = sum(len(b.text) for b in blocks)
    stats = {
        "page_count": None,
        "character_count": total_chars,
        "paragraph_count": sum(1 for b in blocks if b.type == PARAGRAPH),
    }
    return blocks, stats
