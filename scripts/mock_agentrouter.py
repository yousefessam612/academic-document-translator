"""Local mock AgentRouter server for end-to-end testing.

Implements a minimal OpenAI-compatible /v1/chat/completions + /v1/models API
so the full application can be tested without consuming real API credits.
NOT part of the application - development/testing utility only.
"""
from __future__ import annotations

import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Per-request delay (seconds) — pass as CLI arg (e.g. `mock_agentrouter.py 0.8`)
# to simulate slow APIs so interruption/resume can be tested against a running app.
import os
import sys

MOCK_DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else float(os.environ.get("MOCK_DELAY", "0"))

TERM_MAP = {
    "visual impairment": "الإعاقة البصرية",
    "low vision": "ضعف البصر",
    "assistive technology": "التكنولوجيا المساعدة",
    "braille literacy": "محو أمية برايل",
    "students": "الطلاب",
    "education": "التعليم",
    "research": "البحث",
    "chapter": "الفصل",
    "section": "القسم",
    "table": "جدول",
    "introduction": "المقدمة",
}

requests_seen: list[dict] = []


def fake_translate(text: str) -> str:
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for para in paras:
        lines = para.splitlines()
        if len(lines) > 1 and all(" | " in line for line in lines):
            out.append("\n".join(" | ".join(f"({c})" for c in line.split(" | ")) for line in lines))
        else:
            translated = para
            for en, ar in TERM_MAP.items():
                translated = re.sub(re.escape(en), ar, translated, flags=re.IGNORECASE)
            out.append("ترجمة: " + translated)
    return "\n\n".join(out)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    import asyncio

    body = await request.json()
    auth = request.headers.get("authorization", "")
    if auth != "Bearer mock-test-key":
        return JSONResponse(
            status_code=401,
            content={"error": {"message": "Invalid API key", "type": "invalid_request_error"}},
        )
    delay = float(body.get("user_delay", 0) or 0)
    messages = body.get("messages", [])
    user_content = messages[-1]["content"] if messages else ""
    source = user_content.split("### TEXT TO TRANSLATE NOW\n")[-1]
    requests_seen.append({"model": body.get("model"), "chars": len(source), "ts": time.time()})
    if MOCK_DELAY > 0:
        await asyncio.sleep(MOCK_DELAY)
    content = fake_translate(source)
    return {
        "id": "chatcmpl-mock",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": body.get("model", "mock"),
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": len(user_content) // 4, "completion_tokens": len(content) // 3, "total_tokens": 0},
    }


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": "mock-model", "object": "model"}]}


@app.get("/v1/_stats")
async def stats():
    return {"requests": len(requests_seen)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787, log_level="warning")
