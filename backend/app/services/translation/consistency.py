"""Terminology consistency checking across chunks.

Detects when the same English term is translated differently in different
chunks (e.g. 'الإعاقة البصرية' vs 'القصور البصري'). Never modifies
translations automatically — it reports for human review.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class TermUsage:
    english: str
    preferred_arabic: str
    variants: dict[str, list[int]] = field(default_factory=dict)  # arabic -> chunk indexes

    def add(self, arabic: str, chunk_index: int) -> None:
        self.variants.setdefault(arabic, []).append(chunk_index)

    @property
    def consistent(self) -> bool:
        keys = set(self.variants.keys())
        return keys <= {self.preferred_arabic}


class ConsistencyChecker:
    """Per-chunk and cross-chunk terminology consistency analysis."""

    def check_chunk(
        self,
        source_text: str,
        translation: str,
        chunk_index: int,
        dictionary_terms: list[dict],
    ) -> list[dict]:
        """Check one chunk. Returns issue dicts (empty list = clean)."""
        issues: list[dict] = []
        translation_norm = re.sub(r"\s+", " ", translation)
        for term in dictionary_terms:
            english = term["english"].strip()
            preferred = term["arabic"].strip()
            eng_lower = english.lower()
            if len(eng_lower) < 4:
                pattern = rf"\b{re.escape(eng_lower)}\b"
                in_source = re.search(pattern, source_text.lower()) is not None
            else:
                in_source = eng_lower in source_text.lower()
            if not in_source:
                continue
            preferred_norm = re.sub(r"\s+", " ", preferred)
            if preferred_norm and preferred_norm in translation_norm:
                continue  # used preferred translation
            alternatives = [a for a in term.get("alternatives", []) if a.strip()]
            used_alt = next(
                (a for a in alternatives if re.sub(r"\s+", " ", a) in translation_norm), None
            )
            if used_alt:
                issues.append(
                    {
                        "type": "alternative_used",
                        "chunk_index": chunk_index,
                        "english": english,
                        "expected": preferred,
                        "found": used_alt,
                        "message": (
                            f"Chunk {chunk_index}: '{english}' translated as '{used_alt}' "
                            f"(alternative) instead of preferred '{preferred}'."
                        ),
                    }
                )
            else:
                issues.append(
                    {
                        "type": "preferred_missing",
                        "chunk_index": chunk_index,
                        "english": english,
                        "expected": preferred,
                        "found": None,
                        "message": (
                            f"Chunk {chunk_index}: preferred translation '{preferred}' for "
                            f"'{english}' not found in this chunk's translation."
                        ),
                    }
                )
        return issues

    def aggregate_report(
        self, dictionary_terms: list[dict], chunk_results: list[dict]
    ) -> dict:
        """Cross-chunk aggregation.

        chunk_results: [{"chunk_index": i, "source": str, "translation": str}, ...]
        """
        term_map: dict[str, TermUsage] = {}
        term_alternatives: dict[str, list[str]] = {}
        for term in dictionary_terms:
            term_map[term["english"].lower()] = TermUsage(
                english=term["english"], preferred_arabic=term["arabic"]
            )
            term_alternatives[term["english"].lower()] = [
                a for a in term.get("alternatives", []) if a and a.strip()
            ]

        for chunk in chunk_results:
            source = chunk.get("source", "")
            translation = re.sub(r"\s+", " ", chunk.get("translation", ""))
            for key, usage in term_map.items():
                eng_lower = usage.english.lower()
                if len(eng_lower) < 4:
                    if not re.search(rf"\b{re.escape(eng_lower)}\b", source.lower()):
                        continue
                elif eng_lower not in source.lower():
                    continue
                preferred = re.sub(r"\s+", " ", usage.preferred_arabic)
                if preferred and preferred in translation:
                    usage.add(usage.preferred_arabic, chunk["chunk_index"])
                    continue
                used_alt = next(
                    (
                        a
                        for a in term_alternatives.get(key, [])
                        if re.sub(r"\s+", " ", a) in translation
                    ),
                    None,
                )
                if used_alt:
                    usage.add(f"alt: {used_alt}", chunk["chunk_index"])
                else:
                    usage.add("other", chunk["chunk_index"])

        inconsistent: list[dict] = []
        consistent_count = 0
        for usage in term_map.values():
            if not usage.variants:
                continue
            labels = set(usage.variants.keys())
            if len(labels) > 1:
                inconsistent.append(
                    {
                        "english": usage.english,
                        "preferred": usage.preferred_arabic,
                        "used": usage.variants,
                        "chunks_without_preferred": usage.variants.get("other", [])[:20],
                    }
                )
            elif "other" not in labels:
                consistent_count += 1

        return {
            "terms_checked": len(term_map),
            "chunks_checked": len(chunk_results),
            "consistent_terms": consistent_count,
            "inconsistent_terms": inconsistent,
        }
