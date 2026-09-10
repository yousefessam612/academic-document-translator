"""Probe AgentRouter from wherever this runs (datacenter IP check).

Prints the exact status, content-type and body excerpt for:
  1. GET  /v1/models          (works from Back4App container)
  2. POST /v1/chat/completions (failed from Back4App container)
Never prints the API key itself.
"""
import __future__  # noqa: F401
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://agentrouter.org/v1"
KEY = os.environ.get("AGENTROUTER_API_KEY", "")
HEADERS = {
    "Authorization": f"Bearer {KEY}",
    "User-Agent": "codex_cli_rs/0.21.0 (Windows 11; x86_64) unknown",
    "originator": "codex_cli_rs",
    "Content-Type": "application/json",
}

if not KEY:
    print("AGENTROUTER_API_KEY not set")
    sys.exit(1)


def probe(label, url, data=None):
    req = urllib.request.Request(url, data=data, headers=HEADERS, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = r.read().decode("utf-8", "replace")
            print(f"{label}: HTTP {r.status} | content-type: {r.headers.get('content-type')}")
            print(f"  body[:300]: {body[:300]!r}")
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(f"{label}: HTTP {e.code} | content-type: {e.headers.get('content-type')}")
        print(f"  body[:300]: {body[:300]!r}")
        return e.code, body
    except Exception as e:
        print(f"{label}: {type(e).__name__}: {e}")
        return None, ""


print("=== 1. GET /models ===")
probe("GET /models", f"{BASE}/models")

print("\n=== 2. POST /chat/completions (tiny) ===")
payload = json.dumps(
    {
        "model": "glm-5.3",
        "messages": [{"role": "user", "content": "Translate to Arabic: Hello world."}],
        "max_tokens": 500,
        "reasoning_effort": "low",
    }
).encode()
status, body = probe("POST /chat/completions", f"{BASE}/chat/completions", data=payload)

if status == 200 and '"content"' in body:
    print("\nRESULT: POST works from this IP — datacenter IPs are NOT blocked.")
else:
    print("\nRESULT: POST failed/blocked from this IP — AgentRouter blocks datacenter egress.")
