"""Translation engine validation + prompt builder tests."""
from __future__ import annotations

import pytest

from app.services.translation.context_manager import ChunkContext
from app.services.translation.engine import TranslationEngine, TranslationValidationError
from app.services.translation.prompt_builder import PromptBuilder
from app.utils.text import looks_like_json_object, split_sentences, strip_response_prefixes


def make_engine() -> TranslationEngine:
    class DummyProvider:
        name = "dummy"

        async def translate(self, messages):
            raise NotImplementedError

        async def validate_connection(self):
            return True, "ok"

        async def health_check(self):
            return True

        def get_model(self):
            return "dummy"

        def estimate_usage(self, text):
            return None

    return TranslationEngine(DummyProvider())


class TestValidation:
    def test_valid_translation_accepted(self):
        engine = make_engine()
        source = "Visual impairment affects learning.\n\nAssistive technology helps students."
        translation = "تؤثر الإعاقة البصرية على التعلم.\n\nالتكنولوجيا المساعدة تساعد الطلاب."
        engine.validate_translation(source, translation)  # no exception

    def test_empty_rejected(self):
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation("Some source text here.", "   ")

    def test_too_short_rejected(self):
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation("A" * 400, "قصير")

    def test_merged_paragraphs_rejected(self):
        source = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
        translation = "الفقرة الأولى والثانية والثالثة مدمجة في فقرة واحدة طويلة."
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation(source, translation)

    def test_english_output_rejected(self):
        source = "Visual impairment research requires careful methodology and analysis."
        translation = "Visual impairment research requires careful methodology."
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation(source, translation)

    def test_table_row_loss_rejected(self):
        source = "A | B\nC | D\nE | F"
        # Model kept markers for only 2 of 3 rows -> rejected
        translation = "[1] أ | ب\n[2] ج | د"
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation(source, translation)

    def test_table_row_preserved_accepted(self):
        source = "A | B\nC | D\nE | F"
        translation = "[1] أ | ب\n[2] ج | د\n[3] هـ | و"
        make_engine().validate_translation(source, translation)

    def test_table_row_merge_rejected(self):
        source = "A | B\nC | D\nE | F"
        # Model merged rows 2 and 3 into one line -> rejected
        translation = "[1] أ | ب\n[2] ج | د\n[3] هـ"
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation(source, translation)

    def test_arabic_digit_markers_accepted(self):
        source = "A | B\nC | D"
        translation = "[١] أ | ب\n[٢] ج | د"
        make_engine().validate_translation(source, translation)

    def test_wrong_marker_number_rejected(self):
        source = "A | B\nC | D"
        translation = "[1] أ | ب\n[3] ج | د"
        with pytest.raises(TranslationValidationError):
            make_engine().validate_translation(source, translation)


class TestTextUtils:
    def test_split_sentences(self):
        text = "One sentence. Another sentence follows! A third? Yes."
        sentences = split_sentences(text)
        assert len(sentences) == 4

    def test_strip_prefixes(self):
        assert strip_response_prefixes("Translation: النص") == "النص"
        assert strip_response_prefixes("الترجمة: النص") == "النص"

    def test_json_detection(self):
        assert looks_like_json_object('{"a": 1}') is True
        assert looks_like_json_object("plain text") is False


class TestPromptBuilder:
    def test_prompt_contains_all_sections(self):
        ctx = ChunkContext(
            document_title="Book",
            chapter="Chapter 1",
            section="Section 1.1",
            previous_text="previous",
            next_text="next",
            terminology=[{"english": "Low vision", "arabic": "ضعف البصر", "alternatives": []}],
            memory_matches=[{"source": "src", "target": "هدف"}],
        )
        builder = PromptBuilder()
        system_prompt = builder.build_system_prompt(ctx)
        user_prompt = builder.build_user_prompt("The text to translate.", ctx)

        assert "academic translator" in system_prompt
        assert "Output ONLY the translated text" in system_prompt
        assert "[n] markers" in system_prompt or "[n]" in system_prompt
        assert "Low vision => ضعف البصر" in user_prompt
        assert "TRANSLATION MEMORY" in user_prompt
        assert "PREVIOUS CONTEXT" in user_prompt
        assert "NEXT CONTEXT" in user_prompt
        assert "TEXT TO TRANSLATE NOW" in user_prompt
        assert "Chapter 1" in user_prompt
        # Prompts are versioned
        assert builder.version == "1.2"

    def test_table_rows_numbered_in_prompt(self):
        source = "Paragraph one.\n\nA | B\nC | D\nE | F"
        user_prompt = PromptBuilder().build_user_prompt(source, ChunkContext())
        assert "[1] A | B" in user_prompt
        assert "[2] C | D" in user_prompt
        assert "[3] E | F" in user_prompt
        assert "Paragraph one." in user_prompt  # non-table text untouched

    def test_marker_helpers_roundtrip(self):
        from app.services.translation.prompt_builder import (
            extract_row_markers,
            number_table_rows,
            strip_row_markers,
        )

        source = "A | B\nC | D"
        numbered = number_table_rows(source)
        assert extract_row_markers(numbered) == [1, 2]
        assert strip_row_markers(numbered) == source
        assert strip_row_markers("[١] أ | ب") == "أ | ب"

    def test_prompt_no_context_sections_when_empty(self):
        ctx = ChunkContext()
        user_prompt = PromptBuilder().build_user_prompt("text", ctx)
        assert "TERMINOLOGY DICTIONARY" not in user_prompt
        assert "TRANSLATION MEMORY" not in user_prompt
        assert "PREVIOUS CONTEXT" not in user_prompt
