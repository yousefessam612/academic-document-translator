"""Tesseract OCR engine (fully local)."""
from __future__ import annotations

import io

from app.core.config import settings
from app.services.ocr.base import OCREngine


class TesseractEngine(OCREngine):
    name = "tesseract"

    def __init__(self):
        self._tesseract = None
        self._available: bool | None = None

    def _load(self):
        if self._tesseract is None:
            import pytesseract

            if settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
            self._tesseract = pytesseract
        return self._tesseract

    def available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            ts = self._load()
            version = ts.get_tesseract_version()
            self._available = True
            self._version = str(version)
        except Exception:
            self._available = False
        return self._available

    def recognize_png(self, image_bytes: bytes, language: str = "eng") -> str:
        from PIL import Image

        ts = self._load()
        image = Image.open(io.BytesIO(image_bytes))
        try:
            return ts.image_to_string(image, lang=language)
        except ts.TesseractNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "Tesseract OCR is not installed. Install it from "
                "https://github.com/UB-Mannheim/tesseract/wiki or set "
                "TESSERACT_CMD in .env to tesseract.exe."
            ) from exc
