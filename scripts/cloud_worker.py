"""Remote translation worker.

Runs on a trusted machine (home IP) next to nothing else. It pulls pending
chunks from the cloud deployment (which cannot call AgentRouter directly —
its datacenter IP is blocked by the provider's WAF), translates them through
the local AgentRouterProvider, and posts results back.

Usage (from the backend directory):
  .venv\\Scripts\\python.exe ..\\scripts\\cloud_worker.py

Configuration (env or .env):
  WORKER_CLOUD_URL    e.g. https://translator-xxxx.b4a.run
  WORKER_SITE_PASSWORD  the site's APP_ACCESS_PASSWORD (Basic auth)
  WORKER_API_KEY      the server's WORKER_API_KEY
  AGENTROUTER_API_KEY the (working) AgentRouter key — stays local

The loop exits when there is no work; run it whenever a cloud translation is
in progress. Ctrl+C stops it safely — claimed chunks are re-claimed on the
next resume (stuck 'translating' chunks reset to pending server-side).
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.chdir(Path(__file__).resolve().parents[1] / "backend")

from app.core.config import settings  # noqa: E402
from app.services.translation.agentrouter_provider import AgentRouterProvider  # noqa: E402
from app.services.translation.provider import ProviderError  # noqa: E402

CLOUD_URL = os.environ.get("WORKER_CLOUD_URL", "").rstrip("/")
SITE_PASSWORD = os.environ.get("WORKER_SITE_PASSWORD", "")
WORKER_KEY = os.environ.get("WORKER_API_KEY", "")

VALIDATION_RETRIES = 2


def die(msg: str) -> None:
    print(f"ERROR: {msg}")
    raise SystemExit(1)


if not CLOUD_URL:
    die("Set WORKER_CLOUD_URL (e.g. https://translator-xxxx.b4a.run)")
if not WORKER_KEY:
    die("Set WORKER_API_KEY (must match the server's WORKER_API_KEY)")

BASIC = "Basic " + base64.b64encode(f"user:{SITE_PASSWORD}".encode()).decode() if SITE_PASSWORD else ""
HEADERS = {
    "Content-Type": "application/json",
    "X-Worker-Key": WORKER_KEY,
    **({"Authorization": BASIC} if BASIC else {}),
}


def cloud(path: str, method: str = "GET", payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{CLOUD_URL}{path}", data=data, method=method, headers=HEADERS
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            body = resp.read().decode()
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()[:200]
        except Exception:
            detail = str(e)
        return e.code, {"detail": detail}


async def main() -> None:
    provider = AgentRouterProvider()
    if not provider.api_key:
        die("AGENTROUTER_API_KEY missing in local .env")

    status, info = cloud("/api/worker/status")
    if status == 401:
        die(f"Worker key rejected: {info.get('detail')}")
    if status == 503:
        die(f"Server not configured for workers: {info.get('detail')}")
    if status == 404:
        die("Worker mode disabled on server (set WORKER_MODE=true and redeploy).")
    if status != 200:
        die(f"Unexpected status {status}: {info}")
    print(f"connected: {info}")

    idle_polls = 0
    translated_total = 0
    while True:
        status, claim = cloud("/api/worker/claim", "POST", {"limit": 4})
        if status == 401:
            die(f"Worker key rejected: {claim.get('detail')}")
        if status != 200:
            print(f"claim failed ({status}): {claim.get('detail')}")
            await asyncio.sleep(10)
            continue

        tasks = claim.get("tasks", [])
        if not tasks:
            idle_polls += 1
            if idle_polls == 1:
                print("no pending chunks — waiting (Ctrl+C to stop)")
            if idle_polls > 60:  # ~5 minutes idle -> exit
                print("no work for a while; worker exiting.")
                break
            await asyncio.sleep(5)
            continue
        idle_polls = 0

        for task in tasks:
            chunk_no = task["chunk_index"]
            messages = task["messages"]
            attempts = 0
            prompt_tokens = 0
            completion_tokens = 0
            started = time.monotonic()

            # validation-retry loop (mirrors TranslationEngine.translate_chunk)
            while True:
                attempts += 1
                try:
                    result = await provider.translate(messages)
                except ProviderError as exc:
                    reason = f"{type(exc).__name__}: {exc}"[:900]
                    print(f"  chunk {chunk_no}: provider error — {reason[:120]}")
                    status2, _ = cloud(
                        "/api/worker/result",
                        "POST",
                        {
                            "chunk_id": task["chunk_id"],
                            "ok": False,
                            "error": reason,
                            "attempts_done": attempts,
                        },
                    )
                    if status2 != 200:
                        print(f"    result post failed: {status2}")
                    break

                prompt_tokens += result.prompt_tokens
                completion_tokens += result.completion_tokens

                status2, response = cloud(
                    "/api/worker/result",
                    "POST",
                    {
                        "chunk_id": task["chunk_id"],
                        "ok": True,
                        "translation": result.text,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "attempts_done": attempts,
                        **(
                            {"retry_messages": messages}
                            if attempts > 1
                            else {}
                        ),
                    },
                )
                if status2 != 200:
                    print(f"    result post failed: {status2} {response.get('detail', '')[:120]}")
                    break
                if response.get("accepted"):
                    elapsed = int(time.monotonic() - started)
                    print(
                        f"  chunk {chunk_no}: translated OK "
                        f"({len(result.text)} chars, {elapsed}s, attempt {attempts})"
                    )
                    translated_total += 1
                    break
                # rejected by validation -> retry with corrective messages
                retry_messages = response.get("retry_messages")
                if not retry_messages or attempts > VALIDATION_RETRIES:
                    reason = response.get("error", "validation failed")[:900]
                    print(f"  chunk {chunk_no}: rejected — {reason[:120]}")
                    cloud(
                        "/api/worker/result",
                        "POST",
                        {
                            "chunk_id": task["chunk_id"],
                            "ok": False,
                            "error": f"Validation failed after {attempts} attempts: {reason}",
                            "attempts_done": attempts,
                        },
                    )
                    break
                print(f"  chunk {chunk_no}: validation rejected, retrying with correction…")
                messages = retry_messages

    print(f"done. translated {translated_total} chunk(s) this session.")
    await provider.aclose()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nstopped by user")
