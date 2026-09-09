"""TranslationPromptBuilder — the single place where translation prompts live.

Prompts are versioned; behavior changes must bump PROMPT_VERSION.
"""
from __future__ import annotations

import re

from app.services.translation.context_manager import ChunkContext

PROMPT_VERSION = "1.2"

# Row markers the model must preserve for table fidelity: [1], [2], ...
ROW_MARKER_RE = re.compile(r"^\[([0-9\u0660-\u0669]{1,4})\]\s*")


def number_table_rows(text: str) -> str:
    """Prefix every table row (a line containing ' | ') with a [n] marker.

    Markers force 1:1 row fidelity from the model and make validation
    deterministic — the model can no longer merge or drop rows.
    """
    lines = text.split("\n")
    out: list[str] = []
    row_num = 0
    for line in lines:
        if " | " in line:
            row_num += 1
            out.append(f"[{row_num}] {line}")
        else:
            out.append(line)
    return "\n".join(out)


def strip_row_markers(text: str) -> str:
    """Remove [n] row markers the model was asked to preserve."""
    lines = [ROW_MARKER_RE.sub("", line) for line in text.split("\n")]
    return "\n".join(lines)


def normalize_arabic_digits(value: str) -> str:
    table = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return value.translate(table)


def extract_row_markers(text: str) -> list[int]:
    """Return the ordered list of row markers found in the text."""
    markers: list[int] = []
    for line in text.split("\n"):
        m = ROW_MARKER_RE.match(line.strip())
        if m:
            try:
                markers.append(int(normalize_arabic_digits(m.group(1))))
            except ValueError:
                continue
    return markers

_STYLE_HINTS = {
    "Academic": "formal academic Arabic (العربية الأكاديمية الرسمية)",
    "Scientific": "precise scientific Arabic (العربية العلمية الدقيقة)",
    "Educational": "clear educational Arabic suitable for students (العربية التعليمية الواضحة)",
    "Technical": "technical Arabic with precise engineering/technical terms (العربية التقنية)",
    "General": "clear standard modern Arabic (العربية الفصحى المعاصرة)",
}


class PromptBuilder:
    def __init__(self, prompt_version: str = PROMPT_VERSION):
        self.version = prompt_version

    # ------------------------------------------------------------------
    def build_system_prompt(self, ctx: ChunkContext) -> str:
        style_hint = _STYLE_HINTS.get(ctx.style, _STYLE_HINTS["Academic"])
        lines = [
            f"You are a professional academic translator specializing in {ctx.domain}.",
            f"Translate from English into {style_hint}, targeting {ctx.target_language}.",
            "",
            "RULES (follow strictly):",
            "1. Translate the FULL text. Never summarize, paraphrase loosely, omit content, or invent information.",
            "2. Use scientifically appropriate, established Arabic terminology.",
            "3. Keep the same number of paragraphs. Separate paragraphs with exactly one blank line.",
            "4. Keep list structure: one list item per line, same order.",
            "5. Tables are given as numbered lines: each row starts with a marker like [1] followed by cells separated by ' | '. You MUST return the SAME lines with the SAME [n] markers, in the same order, translating only the cell content. Never add, drop, merge, reorder or renumber table rows.",
            "6. Preserve formatting markers: keep **bold** and *italic* markers around the corresponding translated words.",
            "7. Preserve English technical abbreviations/acronyms. On FIRST occurrence in the document write: English abbreviation (Arabic translation); afterwards use the Arabic translation consistently.",
            "8. If the dictionary section provides translations for terms, you MUST use them exactly.",
            "9. If a sentence is ambiguous, preserve the ambiguity. Do not invent a meaning.",
            "10. Output ONLY the translated text. No prefaces like 'Translation:', no notes, no explanations, no comments, no code fences.",
            "11. Do not merge or split sentences across paragraphs.",
        ]
        if ctx.previous_translation_tail:
            lines.append(
                "12. A short excerpt of your previous translation is provided; keep terminology and phrasing consistent with it."
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------
    def build_user_prompt(self, source_text: str, ctx: ChunkContext) -> str:
        parts: list[str] = []

        meta = [f"Document title: {ctx.document_title}"] if ctx.document_title else []
        if ctx.chapter:
            meta.append(f"Chapter: {ctx.chapter}")
        if ctx.section:
            meta.append(f"Section: {ctx.section}")
        meta.append(f"Domain: {ctx.domain}")
        meta.append(f"Style: {ctx.style}")
        parts.append("### DOCUMENT CONTEXT\n" + "\n".join(meta))

        if ctx.terminology:
            dict_lines = [
                f"- {t['english']} => {t['arabic']}" + (
                    f" (alternatives: {', '.join(t['alternatives'])})" if t.get("alternatives") else ""
                )
                for t in ctx.terminology
            ]
            parts.append("### TERMINOLOGY DICTIONARY (use exactly)\n" + "\n".join(dict_lines))

        if ctx.memory_matches:
            tm_lines = [
                f"- SOURCE: {m['source']}\n  TRANSLATION: {m['target']}"
                for m in ctx.memory_matches
            ]
            parts.append(
                "### TRANSLATION MEMORY (previously approved translations; reuse consistent phrasing but adapt to current context)\n"
                + "\n".join(tm_lines)
            )

        if ctx.previous_text:
            parts.append(f"### PREVIOUS CONTEXT (for continuity, do NOT translate it)\n{ctx.previous_text}")

        if ctx.previous_translation_tail:
            parts.append(
                f"### YOUR PREVIOUS TRANSLATION EXCERPT (keep terminology consistent)\n{ctx.previous_translation_tail}"
            )

        if ctx.next_text:
            parts.append(f"### NEXT CONTEXT (for continuity, do NOT translate it)\n{ctx.next_text}")

        parts.append("### TEXT TO TRANSLATE NOW\n" + number_table_rows(source_text))
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    def build_messages(self, source_text: str, ctx: ChunkContext) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self.build_system_prompt(ctx)},
            {"role": "user", "content": self.build_user_prompt(source_text, ctx)},
        ]
