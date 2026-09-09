"""Text utilities: sentence splitting, normalization, token estimation."""
from __future__ import annotations

import hashlib
import re

# Sentence boundary: period/!/? followed by whitespace + capital/start, or Arabic full stop.
_SENTENCE_SPLIT = re.compile(
    r"(?<=[.!?؟])\s+(?=[A-Z\u0621-\u064A0-9\"'(\[])"
)
# Simpler fallback boundary used for very long sentences.
_HARD_SPLIT = re.compile(r"(?<=[.!?؟])\s+")

WORD_RE = re.compile(r"\S+")

# Fragments that should NOT end a sentence: initials ("J.") and common
# abbreviations ("Dr.", "Prof.", "e.g.", "No.", "Fig.", ...).
_ABBREV_RE = re.compile(
    r"^(?:[A-Z]|[A-Za-z]{1,3}|Dr|Prof|Mr|Mrs|Ms|St|etc|e\.g|i\.e|Fig|No|Vol|pp|ed|al)\.$",
    re.IGNORECASE,
)


def split_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving the original whitespace content."""
    if not text or not text.strip():
        return []
    sentences = _SENTENCE_SPLIT.split(text.strip())
    # Merge fragments that are not real sentence ends (initials, abbreviations).
    merged: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if merged and _ABBREV_RE.match(merged[-1]):
            merged[-1] = merged[-1] + " " + sentence
        else:
            merged.append(sentence)
    return merged


def normalize_for_hash(text: str) -> str:
    """Normalize source text for translation-memory hashing."""
    return re.sub(r"\s+", " ", text.strip()).lower()


def hash_text(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode("utf-8")).hexdigest()


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token for English, ~3 for Arabic."""
    arabic_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    other_chars = len(text) - arabic_chars
    return max(1, int(other_chars / 4 + arabic_chars / 3))


def is_mostly_arabic(text: str) -> bool:
    """True when the majority of letters in the text are Arabic."""
    arabic = len(re.findall(r"[\u0600-\u06FF]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return arabic > 0 and arabic >= latin


def strip_code_fences(text: str) -> str:
    """Remove accidental markdown code fences a model may wrap its output in."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            # Drop first fence line (``` or ```text) and the final fence line.
            lines = lines[1:]
            while lines and lines[-1].strip() == "":
                lines.pop()
            if lines and lines[-1].strip().startswith("```"):
                lines.pop()
            stripped = "\n".join(lines).strip()
    return stripped


_PREFIXES = ("translation:", "the translation:", "translated text:", "الترجمة:", "النص المترجم:", "الترجمة:")


def strip_response_prefixes(text: str) -> str:
    """Remove accidental 'Translation:' style prefixes the model may add."""
    stripped = strip_code_fences(text).strip()
    lowered = stripped.lower()
    for prefix in _PREFIXES:
        if lowered.startswith(prefix):
            stripped = stripped[len(prefix):].lstrip(" :\u2013-").strip()
            break
    return stripped


def looks_like_json_object(text: str) -> bool:
    """Heuristic: model accidentally returned a JSON object instead of plain text."""
    stripped = text.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return False
    try:
        import json

        value = json.loads(stripped)
        return isinstance(value, dict)
    except (ValueError, TypeError):
        return False
