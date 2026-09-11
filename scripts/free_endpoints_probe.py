"""Probe free LLM API endpoints from a datacenter IP (no key needed).

A clean 401 JSON response proves the endpoint is reachable from datacenter
IPs (unlike agentrouter.org which serves an Aliyun WAF HTML challenge).
Probes: Groq, OpenRouter, Cerebras, Mistral, together.ai.
"""
import json
import urllib.error
import urllib.request

ENDPOINTS = [
    ("Groq", "https://api.groq.com/openai/v1/chat/completions"),
    ("OpenRouter", "https://openrouter.ai/api/v1/chat/completions"),
    ("Cerebras", "https://api.cerebras.ai/v1/chat/completions"),
    ("Mistral", "https://api.mistral.ai/v1/chat/completions"),
]

payload = json.dumps(
    {"model": "test", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
).encode()

for name, url in ENDPOINTS:
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": "Bearer invalid-key-probe",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read().decode()[:150]
            print(f"{name}: HTTP {r.status} | type={r.headers.get('content-type','')}")
            print(f"   {body!r}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:150]
        ctype = e.headers.get("content-type", "")
        verdict = "REACHABLE (JSON 401)" if "json" in ctype else "BLOCKED/WAF (HTML)"
        print(f"{name}: HTTP {e.code} | type={ctype} | {verdict}")
        print(f"   {body!r}")
    except Exception as e:
        print(f"{name}: {type(e).__name__}: {e}")
    print()
