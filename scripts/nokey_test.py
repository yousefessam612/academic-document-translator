"""Verify the live app fails gracefully when the provider is not configured."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
PDF = r"C:\academic-translator\storage\temp\test_book.pdf"

boundary = "----adtboundary"
with open(PDF, "rb") as fh:
    file_bytes = fh.read()
body = b"".join(
    [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"NoKey_Book.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
        + file_bytes
        + b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
)
r = urllib.request.Request(
    f"{BASE}/documents/upload",
    data=body,
    method="POST",
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
)
with urllib.request.urlopen(r, timeout=60) as resp:
    doc = json.loads(resp.read().decode())
print(f"uploaded: {doc['id'][:8]}")

r = urllib.request.Request(
    f"{BASE}/translation/{doc['id']}/start",
    data=json.dumps({"settings": {}}).encode(),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(r, timeout=60) as resp:
    job = json.loads(resp.read().decode())
print(f"job: {job['id'][:8]}")

for _ in range(30):
    time.sleep(1)
    with urllib.request.urlopen(f"{BASE}/translation/jobs/{job['id']}/progress", timeout=30) as resp:
        p = json.loads(resp.read().decode())
    if p["status"] in ("failed", "completed"):
        break
print(f"status: {p['status']}")
print(f"error:  {p['error_message']}")
assert p["status"] == "failed"
assert "AGENTROUTER" in p["error_message"] or "not configured" in p["error_message"].lower()
print("GRACEFUL CONFIG FAILURE: OK")
