"""OCR engine abstraction. Engines are modular and optional."""
from __future__ import annotations

from abc import ABC, abstractmethod


class OCREngine(ABC):
    """Interface for OCR engines. Add new engines (e.g. PaddleOCR) by implementing this."""

    name: str = "base"

    @abstractmethod
    def available(self) -> bool:
        """Whether the engine's system dependencies are installed."""

    @abstractmethod
    def recognize_png(self, image_bytes: bytes, language: str = "eng") -> str:
        """Run OCR on a PNG image and return recognized text."""


class OCREngineNotAvailable(Exception):
    """Raised when OCR is required but no OCR engine is installed."""
