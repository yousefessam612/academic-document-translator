"""AgentRouterProvider — OpenAI-compatible chat-completions client for AgentRouter.

Configuration (all from .env, never hard-coded):
  AGENTROUTER_API_KEY
  AGENTROUTER_BASE_URL   (default https://agentrouter.org/v1)
  AGENTROUTER_MODEL

The API key never leaves this process; it is never sent to the frontend
and never logged.
"""
from __future__ import annotations

import asyncio
import random

import httpx

from app.core.config import settings
from app.core.logging_config import get_logger
from app.services.translation.provider import (
    AuthenticationError,
    InvalidRequestError,
    ModelResponseError,
    ProviderError,
    ProviderNotConfiguredError,
    ProviderResult,
    RateLimitError,
    TransientAPIError,
    TranslationProvider,
    UsageEstimate,
)
from app.utils.text import estimate_tokens, looks_like_json_object, strip_response_prefixes

logger = get_logger(__name__)


class AgentRouterProvider(TranslationProvider):
    name = "agentrouter"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
        retry_base_delay: float | None = None,
        timeout: float | None = None,
    ):
        self.api_key = (api_key or settings.agentrouter_api_key).strip()
        self.base_url = (base_url or settings.agentrouter_base_url).strip().rstrip("/")
        self.model = (model or settings.agentrouter_model).strip()
        self.max_retries = max_retries if max_retries is not None else settings.max_retries
        self.retry_base_delay = retry_base_delay or settings.retry_base_delay_seconds
        self.timeout = timeout or settings.request_timeout_seconds
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------ client
    def _ensure_client(self) -> httpx.AsyncClient:
        if not self.api_key:
            raise ProviderNotConfiguredError()
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    # AgentRouter's WAF ("unauthorized client detected") rejects
                    # generic HTTP clients; the Codex CLI wire image is accepted
                    # on the OpenAI-compatible endpoint.
                    "User-Agent": settings.agentrouter_client_ua,
                    "originator": settings.agentrouter_originator,
                },
                timeout=self.timeout,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    def _require_config(self) -> None:
        if not self.api_key:
            raise ProviderNotConfiguredError(
                "AGENTROUTER_API_KEY is missing. Add it to the .env file."
            )

    # ------------------------------------------------------------- translate
    async def translate(self, messages: list[dict[str, str]]) -> ProviderResult:
        self._require_config()
        client = self._ensure_client()
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            # Reasoning models need headroom for reasoning tokens before the
            # visible content is produced; a low cap yields empty content.
            "max_tokens": settings.agentrouter_max_tokens,
        }
        if settings.agentrouter_reasoning_effort:
            payload["reasoning_effort"] = settings.agentrouter_reasoning_effort

        attempt = 0
        last_error: ProviderError | None = None
        while attempt < max(1, self.max_retries):
            attempt += 1
            # Escalate the token cap on retries: a reasoning model can exhaust
            # max_tokens thinking and return empty/truncated content; doubling
            # the headroom makes the retry meaningful.
            payload["max_tokens"] = min(
                settings.agentrouter_max_tokens * (2 ** (attempt - 1)), 32768
            )
            try:
                response = await client.post("/chat/completions", json=payload)
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = TransientAPIError(f"Network error: {type(exc).__name__}")
                logger.warning(
                    "Provider network error",
                    extra={"operation": "translate", "status": "error", "attempt": attempt,
                           "error_type": type(exc).__name__},
                )
            except httpx.HTTPError as exc:
                last_error = TransientAPIError(f"HTTP error: {type(exc).__name__}")
                logger.warning(
                    "Provider HTTP error",
                    extra={"operation": "translate", "status": "error", "attempt": attempt,
                           "error_type": type(exc).__name__},
                )
            else:
                error = self._map_status(response.status_code, response.text)
                if error is None:
                    data = self._safe_json(response)
                    if data is None:
                        # A 200 with a non-JSON body is a WAF/proxy block page
                        # (AgentRouter's Aliyun WAF serves an HTML JS-challenge
                        # to datacenter IPs). Retryable, but with a clear cause.
                        last_error = ModelResponseError(
                            "Provider returned a non-JSON response (content-type: "
                            f"{response.headers.get('content-type', 'unknown')}, body starts: "
                            f"{response.text[:80]!r}). This is typically a WAF/proxy "
                            "block page — the API is unreachable from this host's network."
                        )
                        logger.warning(
                            "Provider returned non-JSON (WAF?) response",
                            extra={
                                "operation": "translate",
                                "status": "retry",
                                "attempt": attempt,
                                "error_type": "non_json_response",
                            },
                        )
                    else:
                        try:
                            return self._parse_response(data)
                        except ModelResponseError as exc:
                            # Malformed/empty/truncated model output — retryable.
                            last_error = exc
                            logger.warning(
                                "Provider response rejected",
                                extra={
                                    "operation": "translate",
                                    "status": "retry",
                                    "attempt": attempt,
                                    "error_type": "model_response",
                                },
                            )
                else:
                    last_error = error
                    logger.warning(
                        "Provider API error",
                        extra={
                            "operation": "translate",
                            "status": "error",
                            "attempt": attempt,
                            "error_type": type(error).__name__,
                            "http_status": response.status_code,
                        },
                    )
                    if not error.retryable:
                        raise error

            if attempt < self.max_retries:
                delay = self.retry_base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
                logger.info(
                    "Retrying translation request",
                    extra={"operation": "translate", "status": "retry", "attempt": attempt,
                           "delay_seconds": round(delay, 1)},
                )
                await asyncio.sleep(delay)

        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _safe_json(response: httpx.Response) -> dict | None:
        """Parse a JSON object body; None when the body is not JSON (WAF pages,
        HTML errors, empty bodies)."""
        content_type = (response.headers.get("content-type") or "").lower()
        if "json" not in content_type:
            return None
        try:
            data = response.json()
        except (ValueError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @staticmethod
    def _map_status(status_code: int, body: str) -> ProviderError | None:
        """Map an HTTP status to a typed error; None means success."""
        if status_code < 400:
            return None
        excerpt = body[:300] if body else ""
        if status_code in (401, 403):
            return AuthenticationError(f"HTTP {status_code}: {excerpt}")
        if status_code == 429:
            return RateLimitError(f"HTTP 429: {excerpt}")
        if status_code == 400:
            return InvalidRequestError(f"HTTP 400: {excerpt}")
        if status_code in (402,):
            return ProviderError(
                f"HTTP 402 (payment/credit issue): {excerpt}", retryable=False
            )
        return TransientAPIError(f"HTTP {status_code}: {excerpt}")

    def _parse_response(self, data: dict) -> ProviderResult:
        """Validate the chat-completions payload and extract the translation."""
        if not isinstance(data, dict):
            raise ModelResponseError("Response is not a JSON object.")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ModelResponseError("Response contains no choices.")
        choice = choices[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if content is None and isinstance(choice.get("text"), str):
            content = choice["text"]  # legacy completions shape
        if not isinstance(content, str) or not content.strip():
            finish = choice.get("finish_reason")
            if finish == "length":
                raise ModelResponseError(
                    "The model exhausted the token limit before producing "
                    "translation text (reasoning consumed the budget). "
                    "Retrying with a larger limit."
                )
            raise ModelResponseError("Response content is empty.")

        text = strip_response_prefixes(content)

        # A length-finish means the output was cut mid-translation — reject
        # even when content exists, and retry with a larger cap.
        if choice.get("finish_reason") == "length":
            raise ModelResponseError(
                "The translation was truncated by the token limit. "
                "Retrying with a larger limit."
            )

        # Detect corrupted / wrapped output.
        if looks_like_json_object(text):
            raise ModelResponseError("Model returned a JSON object instead of translation text.")
        if "### TEXT TO TRANSLATE NOW" in text or "TERMINOLOGY DICTIONARY" in text:
            raise ModelResponseError("Model echoed the prompt instead of translating.")
        if text.strip().startswith("Note:") or text.strip().startswith("Explanation:"):
            raise ModelResponseError("Model added explanation text instead of translating.")
        if not text.strip():
            raise ModelResponseError("Translation is empty after cleaning.")

        usage = data.get("usage") or {}
        return ProviderResult(
            text=text,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            model=data.get("model", self.model),
            raw_content=content,
        )

    # --------------------------------------------------------- introspection
    async def validate_connection(self) -> tuple[bool, str]:
        try:
            self._require_config()
        except ProviderNotConfiguredError as exc:
            return False, str(exc)
        client = self._ensure_client()
        try:
            response = await client.get("/models")
        except httpx.HTTPError as exc:
            return False, f"Cannot reach {self.base_url}: {type(exc).__name__}"
        if response.status_code in (401, 403):
            return False, "Authentication failed. Check AGENTROUTER_API_KEY."
        if response.status_code >= 400:
            return False, f"Provider returned HTTP {response.status_code}."
        # A 200 with a non-JSON body is the WAF JS-challenge page served to
        # datacenter IPs — the API is effectively unreachable from this host.
        if self._safe_json(response) is None:
            return False, (
                "Provider returned a block page instead of the API "
                "(datacenter IP blocked by the provider's WAF). Use remote "
                "worker mode (WORKER_MODE=true) so a trusted machine performs "
                "the LLM calls."
            )
        return True, f"Connected to {self.base_url} (model: {self.model})."

    async def health_check(self) -> bool:
        ok, _ = await self.validate_connection()
        return ok

    def get_model(self) -> str:
        return self.model

    def estimate_usage(self, source_text: str) -> UsageEstimate:
        input_tokens = estimate_tokens(source_text)
        # Arabic output is typically 0.9-1.1x source length in tokens.
        return UsageEstimate(
            input_tokens=input_tokens,
            output_tokens=int(input_tokens * 1.0),
            characters=len(source_text),
        )
