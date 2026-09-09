"""TranslationProvider interface + error taxonomy.

The rest of the application depends ONLY on this interface, so a different
provider (DeepL, Azure, local model, ...) can be added without touching
the rest of the codebase.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ProviderResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    raw_content: str = ""


@dataclass
class UsageEstimate:
    input_tokens: int = 0
    output_tokens: int = 0
    characters: int = 0
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------- errors
class ProviderError(Exception):
    """Base class for provider failures."""

    user_message = "Translation service error."
    retryable = False

    def __init__(self, message: str | None = None, retryable: bool | None = None):
        # Only override the class-level default when explicitly requested,
        # so subclasses like RateLimitError keep retryable=True.
        if retryable is not None:
            self.retryable = retryable
        super().__init__(message or self.user_message)


class AuthenticationError(ProviderError):
    user_message = "Translation service authentication failed. Check your API configuration (AGENTROUTER_API_KEY)."
    retryable = False


class RateLimitError(ProviderError):
    user_message = "Translation service rate limit reached. The request will be retried with backoff."
    retryable = True


class TransientAPIError(ProviderError):
    user_message = "Translation service is temporarily unavailable. The request will be retried."
    retryable = True


class InvalidRequestError(ProviderError):
    user_message = "The translation service rejected the request (invalid request)."
    retryable = False


class ModelResponseError(ProviderError):
    """Model returned empty / malformed / corrupted output."""

    user_message = "The translation model returned a malformed response."
    retryable = True


class ProviderNotConfiguredError(ProviderError):
    user_message = (
        "Translation provider is not configured. Set AGENTROUTER_API_KEY and "
        "AGENTROUTER_MODEL in the .env file."
    )
    retryable = False


class TranslationProvider(ABC):
    """Interface every translation provider must implement."""

    name: str = "base"

    @abstractmethod
    async def translate(self, messages: list[dict[str, str]]) -> ProviderResult:
        """Translate one prompt (list of chat messages). Raises ProviderError subclasses."""

    @abstractmethod
    async def validate_connection(self) -> tuple[bool, str]:
        """Return (ok, human-readable detail)."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap liveness probe."""

    @abstractmethod
    def get_model(self) -> str:
        """Return the configured model identifier."""

    @abstractmethod
    def estimate_usage(self, source_text: str) -> UsageEstimate:
        """Estimate token usage for a piece of source text."""
