"""Translation engine: orchestrates single-chunk translation with validation.

Retry layers:
  1. AgentRouterProvider retries temporary API failures (network / 429 / 5xx)
     with exponential backoff.
  2. The engine re-prompts (up to VALIDATION_RETRIES) when the model returns
     structurally invalid output (dropped paragraphs, table corruption,
     non-Arabic output for English source).

Nothing is faked: on final failure the chunk is marked failed with the error.
"""
from __future__ import annotations

import re
import time

from sqlalchemy.orm import Session

from app.core.logging_config import get_logger
from app.models.chunk import TranslationChunk
from app.services.terminology.memory import TranslationMemoryService
from app.services.terminology.service import TerminologyService
from app.services.translation.context_manager import ChunkContext, ContextManager
from app.services.translation.consistency import ConsistencyChecker
from app.services.translation.prompt_builder import (
    PromptBuilder,
    extract_row_markers,
    normalize_arabic_digits,
    number_table_rows,
    strip_row_markers,
)
from app.services.translation.provider import ModelResponseError, TranslationProvider
from app.utils.text import estimate_tokens

logger = get_logger(__name__)

VALIDATION_RETRIES = 2
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]{3,}")


class TranslationValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _marked_cell_counts(text: str) -> dict[int, int]:
    """marker -> number of cells in that table row."""
    from app.services.translation.prompt_builder import ROW_MARKER_RE

    counts: dict[int, int] = {}
    for line in text.split("\n"):
        m = ROW_MARKER_RE.match(line.strip())
        if m:
            try:
                num = int(normalize_arabic_digits(m.group(1)))
            except ValueError:
                continue
            counts[num] = line.count(" | ") + 1
    return counts


class TranslationEngine:
    def __init__(
        self,
        provider: TranslationProvider,
        prompt_builder: PromptBuilder | None = None,
        context_manager: ContextManager | None = None,
    ):
        self.provider = provider
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.context_manager = context_manager or ContextManager()
        self.consistency = ConsistencyChecker()

    # ------------------------------------------------------------------
    def validate_translation(self, source_text: str, translation: str) -> None:
        """Structural validation. Raises TranslationValidationError."""
        if not translation or not translation.strip():
            raise TranslationValidationError("Translation is empty.")

        if len(translation.strip()) < max(10, len(source_text.strip()) * 0.25):
            raise TranslationValidationError(
                "Translation is suspiciously short compared to the source "
                "(possible omission or summarization)."
            )

        # Table rows are sent numbered ([1], [2], ...). Every row marker must
        # come back exactly once with the same cell count — no merged, dropped
        # or reshaped rows.
        numbered_source = number_table_rows(source_text)
        expected_markers = extract_row_markers(numbered_source)
        if expected_markers:
            got_markers = extract_row_markers(translation)
            if got_markers != expected_markers:
                missing = sorted(set(expected_markers) - set(got_markers))
                extra = sorted(set(got_markers) - set(expected_markers))
                raise TranslationValidationError(
                    f"Table row markers mismatch: expected {len(expected_markers)} rows "
                    f"but got {len(got_markers)}."
                    + (f" Missing rows: {missing[:10]}." if missing else "")
                    + (f" Unexpected rows: {extra[:10]}." if extra else "")
                    + " Keep every [n] row marker exactly as given."
                )
            src_cells = _marked_cell_counts(numbered_source)
            out_cells = _marked_cell_counts(translation)
            reshaped = [
                n for n in expected_markers if src_cells.get(n) != out_cells.get(n)
            ]
            if reshaped:
                raise TranslationValidationError(
                    f"Table rows changed column count: rows {sorted(reshaped)[:10]} "
                    "must keep the same number of ' | ' separated cells."
                )

        src_paras = _split_paragraphs(source_text)
        out_paras = _split_paragraphs(translation)
        # Source blocks are joined with blank lines; the model must keep them.
        if out_paras and src_paras and len(out_paras) < max(1, len(src_paras) - 1):
            raise TranslationValidationError(
                f"Paragraph count mismatch: source has {len(src_paras)} paragraphs "
                f"but translation has {len(out_paras)} (content may have been merged or dropped)."
            )

        # Arabic presence: English source with several English words must yield Arabic.
        if len(_ENGLISH_WORD_RE.findall(source_text)) >= 8 and not _ARABIC_RE.search(translation):
            raise TranslationValidationError(
                "Translation contains no Arabic text while the source is English."
            )

    # ------------------------------------------------------------------
    async def translate_chunk(
        self,
        source_text: str,
        chunk_index: int,
        ctx: ChunkContext,
    ) -> tuple[str, dict]:
        """Translate one chunk. Returns (translation, info dict with usage/issues)."""
        info: dict = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "consistency_issues": [],
            "attempts": 0,
            "duration_ms": 0,
        }
        started = time.monotonic()

        messages = self.prompt_builder.build_messages(source_text, ctx)
        last_validation_error: TranslationValidationError | None = None

        for attempt in range(1, VALIDATION_RETRIES + 2):
            info["attempts"] = attempt
            result = await self.provider.translate(messages)
            info["prompt_tokens"] += result.prompt_tokens
            info["completion_tokens"] += result.completion_tokens
            translation = result.text
            try:
                self.validate_translation(source_text, translation)
                info["duration_ms"] = int((time.monotonic() - started) * 1000)
                # Clean translation: remove the [n] table row markers we asked
                # the model to preserve (they served validation only).
                translation = strip_row_markers(translation)
                # Per-chunk consistency check (non-blocking warnings).
                if ctx.terminology:
                    info["consistency_issues"] = self.consistency.check_chunk(
                        source_text, translation, chunk_index, ctx.terminology
                    )
                return translation, info
            except TranslationValidationError as exc:
                last_validation_error = exc
                logger.warning(
                    "Translation validation failed",
                    extra={
                        "operation": "translate_chunk",
                        "status": "retry",
                        "chunk_index": chunk_index,
                        "attempt": attempt,
                        "error_type": "validation",
                    },
                )
                # Ask the model to fix the specific structural problem.
                messages = self.prompt_builder.build_messages(source_text, ctx)
                messages.append({"role": "assistant", "content": translation})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous output was rejected: "
                            f"{exc.message}\n"
                            "Please output the complete translation again, following ALL "
                            "rules exactly: same paragraph count with blank lines between "
                            "paragraphs, every table row keeping its exact [n] marker in "
                            "order, Arabic output only."
                        ),
                    }
                )

        info["duration_ms"] = int((time.monotonic() - started) * 1000)
        raise ModelResponseError(
            f"Model output failed validation after {VALIDATION_RETRIES + 1} attempts: "
            f"{last_validation_error.message if last_validation_error else 'unknown'}"
        )

    # ------------------------------------------------------------------
    def build_chunk_context(
        self,
        db: Session,
        chunk: TranslationChunk,
        document_title: str,
        job_settings: dict,
        previous_chunk: TranslationChunk | None,
        next_chunk: TranslationChunk | None,
    ) -> ChunkContext:
        domains = []
        style = job_settings.get("style", "Academic")
        domain = job_settings.get("domain", "General")
        if job_settings.get("use_global_dictionary", True):
            domains.append("General")
        if job_settings.get("use_domain_dictionary", True) and domain != "General":
            domains.append(domain)
        if job_settings.get("use_custom_dictionary", True):
            domains.append("Custom")

        terminology: list[dict] = []
        if domains:
            term_service = TerminologyService(db)
            terminology = term_service.relevant_terms_for_text(chunk.source_text, domains)

        memory_matches: list[dict] = []
        if job_settings.get("use_translation_memory", True):
            tm = TranslationMemoryService(db)
            memory_matches = tm.lookup(chunk.source_text)

        ctx = self.context_manager.build(
            document_title=document_title,
            chapter=chunk.chapter,
            section=chunk.section,
            previous_chunk_text=previous_chunk.source_text if previous_chunk else None,
            previous_chunk_translation=previous_chunk.translation if previous_chunk else None,
            next_chunk_text=next_chunk.source_text if next_chunk else None,
        )
        ctx.terminology = terminology
        ctx.memory_matches = memory_matches
        ctx.style = style
        ctx.domain = domain
        ctx.target_language = job_settings.get("target_language", "Arabic")
        return ctx

    @staticmethod
    def token_estimate(text: str) -> int:
        return estimate_tokens(text)
