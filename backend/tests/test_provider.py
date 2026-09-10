"""AgentRouterProvider tests with a mocked HTTP transport.

No real API calls are made — zero credit consumption.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.services.translation.provider import (
    AuthenticationError,
    InvalidRequestError,
    ModelResponseError,
    ProviderNotConfiguredError,
    RateLimitError,
    TransientAPIError,
)
from app.services.translation.agentrouter_provider import AgentRouterProvider


def make_provider(handler, retries: int = 3, base_delay: float = 0.0) -> AgentRouterProvider:
    provider = AgentRouterProvider(
        api_key="test-key-not-real",
        base_url="https://agentrouter.test/v1",
        model="test-model",
        max_retries=retries,
        retry_base_delay=base_delay,
    )
    transport = httpx.MockTransport(handler)
    provider._client = httpx.AsyncClient(
        base_url=provider.base_url,
        headers={"Authorization": "Bearer test-key-not-real"},
        transport=transport,
    )
    return provider


def ok_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "model": "test-model",
        },
    )


class TestSuccess:
    def test_translate_ok(self):
        provider = make_provider(lambda request: ok_response("النص العربي المترجم"))

        async def run():
            result = await provider.translate(
                [{"role": "user", "content": "Translate this"}]
            )
            return result

        result = asyncio.run(run())
        assert result.text == "النص العربي المترجم"
        assert result.prompt_tokens == 100
        assert result.completion_tokens == 50

    def test_translate_strips_translation_prefix(self):
        provider = make_provider(lambda request: ok_response("Translation: النص"))

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        assert asyncio.run(run()).text == "النص"

    def test_translate_strips_code_fences(self):
        provider = make_provider(lambda request: ok_response("```\nالنص\n```"))

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        assert asyncio.run(run()).text == "النص"


class TestErrorMapping:
    def test_auth_error_not_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(401, json={"error": "bad key"})

        provider = make_provider(handler)

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(AuthenticationError):
            asyncio.run(run())
        assert calls["n"] == 1, "auth errors must fail fast"

    def test_invalid_request_not_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(400, json={"error": "bad request"})

        provider = make_provider(handler)

        with pytest.raises(InvalidRequestError):
            asyncio.run(provider.translate([{"role": "user", "content": "x"}]))
        assert calls["n"] == 1

    def test_rate_limit_retried_then_succeeds(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, json={"error": "rate limited"})
            return ok_response("بعد إعادة المحاولة")

        provider = make_provider(handler)

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        result = asyncio.run(run())
        assert result.text == "بعد إعادة المحاولة"
        assert calls["n"] == 3

    def test_server_error_retried_then_fails(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(503, json={"error": "unavailable"})

        provider = make_provider(handler)

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(TransientAPIError):
            asyncio.run(run())
        assert calls["n"] == 3, "must stop after max retries"

    def test_payment_error_not_retried(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(402, json={"error": "insufficient credits"})

        provider = make_provider(handler)

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(Exception) as exc_info:
            asyncio.run(run())
        assert not isinstance(exc_info.value, TransientAPIError)
        assert calls["n"] == 1


class TestResponseValidation:
    def test_empty_content_raises(self):
        provider = make_provider(lambda request: ok_response("   "))

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ModelResponseError):
            asyncio.run(run())

    def test_length_finish_with_empty_content_retries_with_bigger_cap(self):
        """Reasoning-model failure mode: finish=length + empty content.

        The provider must retry with an escalated max_tokens and succeed once
        the model returns a normal response.
        """
        calls = {"n": 0}
        caps: list[int] = []

        def handler(request):
            import json as _json

            calls["n"] += 1
            caps.append(_json.loads(request.content).get("max_tokens"))
            if calls["n"] == 1:
                # reasoning exhausted the budget -> empty content, finish=length
                return httpx.Response(
                    200,
                    json={
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": "", "reasoning_content": "thinking..."},
                                "finish_reason": "length",
                            }
                        ],
                        "usage": {"prompt_tokens": 100, "completion_tokens": 8192},
                    },
                )
            return ok_response("الترجمة العربية الكاملة")

        provider = make_provider(handler)

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        result = asyncio.run(run())
        assert result.text == "الترجمة العربية الكاملة"
        assert calls["n"] == 2
        from app.core.config import settings as app_settings

        assert caps[0] == app_settings.agentrouter_max_tokens
        assert caps[1] == caps[0] * 2, "retry must escalate the token cap"

    def test_length_finish_with_content_rejected_as_truncated(self):
        """finish=length with non-empty content means truncation -> retryable error."""

        def handler(request):
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "نص مبتور"},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 100},
                },
            )

        provider = make_provider(handler)

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ModelResponseError, match="truncated|token limit"):
            asyncio.run(run())

    def test_json_corruption_raises(self):
        provider = make_provider(
            lambda request: ok_response('{"translation": "النص", "note": "hi"}')
        )

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ModelResponseError):
            asyncio.run(run())

    def test_prompt_echo_raises(self):
        provider = make_provider(
            lambda request: ok_response("### TEXT TO TRANSLATE NOW\nsome text")
        )

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ModelResponseError):
            asyncio.run(run())

    def test_missing_choices_raises(self):
        provider = make_provider(lambda request: httpx.Response(200, json={}))

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ModelResponseError):
            asyncio.run(run())


class TestConfiguration:
    def test_not_configured_raises(self):
        provider = AgentRouterProvider(api_key="", model="", base_url="https://x/v1")

        async def run():
            await provider.translate([{"role": "user", "content": "x"}])

        with pytest.raises(ProviderNotConfiguredError):
            asyncio.run(run())

    def test_gemini_mode_drops_codex_wire_and_reasoning(self):
        """Gemini's OpenAI-compatible endpoint must not receive the Codex
        client headers (WAF workaround) nor reasoning_effort."""
        provider = AgentRouterProvider(
            api_key="gk-test",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model="gemini-2.5-flash",
        )
        assert provider._is_gemini is True
        seen: dict = {}

        def handler(request):
            seen["headers"] = dict(request.headers)
            seen["payload"] = json.loads(request.content)
            return ok_response("النص")

        provider._client = httpx.AsyncClient(
            base_url=provider.base_url,
            headers={"Authorization": "Bearer gk-test"},
            transport=httpx.MockTransport(handler),
        )

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        result = asyncio.run(run())
        assert result.text == "النص"
        # no codex wire headers injected on the Gemini path
        assert "originator" not in seen["headers"]
        assert "codex" not in seen["headers"].get("user-agent", "")
        # no reasoning_effort in the payload
        assert "reasoning_effort" not in seen["payload"]
        assert seen["payload"]["model"] == "gemini-2.5-flash"

    def test_agentrouter_mode_keeps_reasoning_effort(self):
        provider = AgentRouterProvider(
            api_key="k", base_url="https://agentrouter.org/v1", model="glm-5.3"
        )
        seen: dict = {}

        def handler(request):
            seen["payload"] = json.loads(request.content)
            return ok_response("النص")

        provider._client = httpx.AsyncClient(
            base_url=provider.base_url,
            headers={"Authorization": "Bearer k"},
            transport=httpx.MockTransport(handler),
        )

        async def run():
            return await provider.translate([{"role": "user", "content": "x"}])

        asyncio.run(run())
        assert seen["payload"].get("reasoning_effort") == "low"

    def test_missing_model_falls_back_to_default(self):
        """The model defaults to glm-5.3; only a missing key is fatal."""
        provider = AgentRouterProvider(api_key="k", model="", base_url="https://x/v1")
        assert provider.get_model() == "glm-5.3"

    def test_validate_connection_ok(self):
        def handler(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json={"data": []})
            return httpx.Response(404)

        provider = make_provider(handler)

        async def run():
            return await provider.validate_connection()

        ok, detail = asyncio.run(run())
        assert ok is True

    def test_validate_connection_auth_fail(self):
        def handler(request):
            return httpx.Response(401, json={"error": "unauthorized"})

        provider = make_provider(handler)

        async def run():
            return await provider.validate_connection()

        ok, detail = asyncio.run(run())
        assert ok is False
        assert "Authentication" in detail

    def test_estimate_usage(self):
        provider = AgentRouterProvider(api_key="k", base_url="https://x", model="m")
        estimate = provider.estimate_usage("A " * 400)
        assert estimate.input_tokens > 0
        assert estimate.characters == 800

    def test_get_model(self):
        provider = AgentRouterProvider(api_key="k", base_url="https://x", model="my-model")
        assert provider.get_model() == "my-model"
