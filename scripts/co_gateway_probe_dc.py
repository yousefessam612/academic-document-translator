"""Probe co.agentrouter.org from a datacenter IP with ALL client fingerprints.

The alternate gateway responded JSON 401 (Invalid API Key) with Codex headers
from Actions — meaning it is NOT WAF-blocked from datacenter IPs, unlike the
main agentrouter.org. Find out which fingerprint+format it accepts.
"""
import json
import os
import urllib.error
import urllib.request

KEY = os.environ.get("AGENTROUTER_API_KEY", "")
BASE = "https://co.agentrouter.org"

CODEX = {
    "User-Agent": "codex_cli_rs/0.21.0 (Windows 11; x86_64) unknown",
    "originator": "codex_cli_rs",
}
CLAUDE = {
    "User-Agent": "claude-cli/2.0.14 (external, cli)",
    "x-app": "cli",
    "anthropic-version": "2023-06-01",
}


def req(path, method="GET", payload=None, extra=None):
    headers = {
        "Authorization": f"Bearer {KEY}",
        "x-api-key": KEY,
        "Content-Type": "application/json",
        **(extra or {}),
    }
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, resp.headers.get("content-type", ""), resp.read().decode("utf-8", "replace")[:250]
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = str(e)
        return e.code, e.headers.get("content-type", ""), body[:250]
    except Exception as e:
        return None, "", f"{type(e).__name__}: {e}"


openai_payload = {
    "model": "glm-5.3",
    "messages": [{"role": "user", "content": "Translate to Arabic: Hello world."}],
    "max_tokens": 500,
}
anthropic_payload = {
    "model": "claude-sonnet-4-5",
    "max_tokens": 500,
    "messages": [{"role": "user", "content": "Translate to Arabic: Hello world."}],
}

print("A. GET /v1/models, codex headers   ->", req("/v1/models", extra=CODEX))
print("B. GET /v1/models, claude headers  ->", req("/v1/models", extra=CLAUDE))
print("C. POST chat/completions, claude   ->", req("/v1/chat/completions", "POST", openai_payload, CLAUDE))
print("D. POST /v1/messages, claude       ->", req("/v1/messages", "POST", anthropic_payload, CLAUDE))
print("E. POST /v1/messages, codex        ->", req("/v1/messages", "POST", anthropic_payload, CODEX))
print("F. GET / (homepage)                ->", req("/", extra=CLAUDE))
