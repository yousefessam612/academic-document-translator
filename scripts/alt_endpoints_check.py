"""Test alternate OpenAI-compatible endpoints that might work from datacenter IPs.

1. co.agentrouter.org (AgentRouter's alternate gateway) with Codex wire headers
2. models.github.ai (GitHub Models) with the local gh token

Run from GitHub Actions (datacenter IP) to mirror the cloud deployment's network.
Never prints full keys.
"""
import json
import os
import sys
import urllib.error
import urllib.request

AR_KEY = os.environ.get("AGENTROUTER_API_KEY", "")
GH_TOKEN = os.environ.get("GH_MODELS_TOKEN", "")


def post(url, key, payload, extra_headers=None):
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read().decode("utf-8", "replace")
            ctype = r.headers.get("content-type", "")
            return r.status, ctype, body[:300]
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = str(e)
        return e.code, e.headers.get("content-type", ""), body[:300]
    except Exception as e:
        return None, "", f"{type(e).__name__}: {e}"


payload_ar = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "Translate to Arabic: Hello world."}],
    "max_tokens": 1000,
    "reasoning_effort": "low",
}
codex_headers = {
    "User-Agent": "codex_cli_rs/0.21.0 (Windows 11; x86_64) unknown",
    "originator": "codex_cli_rs",
}

print("=== 1. co.agentrouter.org (alternate gateway, codex headers) ===")
if AR_KEY:
    s, ct, body = post(
        "https://co.agentrouter.org/v1/chat/completions", AR_KEY, payload_ar, codex_headers
    )
    print(f"status={s} content-type={ct}")
    print(f"body: {body!r}")
    ok1 = s == 200 and "json" in ct and '"content"' in body
    print("VERDICT:", "WORKS from datacenter" if ok1 else "blocked/unusable")
else:
    print("no AR key set")
    ok1 = False

print("\n=== 2. models.github.ai (GitHub Models, gh token) ===")
payload_gh = {
    "model": "openai/gpt-4o-mini",
    "messages": [{"role": "user", "content": "Translate to Arabic: Hello world."}],
    "max_tokens": 200,
}
if GH_TOKEN:
    s, ct, body = post(
        "https://models.github.ai/inference/chat/completions", GH_TOKEN, payload_gh
    )
    print(f"status={s} content-type={ct}")
    print(f"body: {body!r}")
    ok2 = s == 200 and '"content"' in body
    print("VERDICT:", "WORKS" if ok2 else "unusable with this token")
else:
    print("no GH token set")
    ok2 = False

print("\nSUMMARY: agentrouter-alt=%s github-models=%s" % (ok1, ok2))
