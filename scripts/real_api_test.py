"""Real-API E2E test: translate a small document through the live AgentRouter.

Uses a larger chunk size to keep the number of chunks (and credit usage) low.
"""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
PDF = r"C:\academic-translator\storage\temp\test_book.pdf"
OUT = r"C:\academic-translator\storage\temp\real_api_translated.docx"


def req(path, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(f"{BASE}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=180) as resp:
        if resp.status == 204:
            return None
        return json.loads(resp.read().decode())


with open(PDF, "rb") as fh:
    file_bytes = fh.read()
boundary = "----adtboundary"
body = b"".join(
    [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"Real_API_Book.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
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
with urllib.request.urlopen(r, timeout=120) as resp:
    doc = json.loads(resp.read().decode())
print(f"1. Uploaded {doc['original_filename']} ({doc['file_size']} bytes)")

job = req(
    f"/translation/{doc['id']}/start",
    method="POST",
    data={
        "settings": {
            "style": "Academic",
            "domain": "Visual Impairment",
            "use_global_dictionary": True,
            "use_domain_dictionary": True,
            "use_translation_memory": True,
            "chunk_target_chars": 1500,
        }
    },
)
print(f"2. Job {job['id'][:8]} started (model: real AgentRouter / glm-5.3)")

final = None
last = None
for i in range(600):
    time.sleep(2)
    p = req(f"/translation/jobs/{job['id']}/progress")
    marker = (p["status"], p["completed_chunks"], p["failed_chunks"])
    if marker != last or p["status"] in ("completed", "failed", "cancelled"):
        print(f"   {p['status']:12s} {p['progress_percentage']:5.1f}%  {p['completed_chunks']}/{p['total_chunks']} failed={p['failed_chunks']}")
        last = marker
    if p["status"] in ("completed", "failed", "cancelled"):
        final = p
        break
assert final, "job did not finish in time"
print(f"3. Final: {final['status']}")

if final["status"] != "completed":
    print("ERROR:", final["error_message"])
    for e in final["recent_errors"]:
        print("  ", e)
    raise SystemExit(1)

job = req(f"/translation/jobs/{job['id']}")
qr = job["quality_report"]
print(f"4. Quality: {qr['completed_chunks']}/{qr['total_chunks']} chunks | consistent terms: {qr['terminology']['consistent_terms']} | inconsistent: {len(qr['terminology']['inconsistent_terms'])}")

with urllib.request.urlopen(f"{BASE}/documents/{doc['id']}/download/translated", timeout=120) as resp:
    data = resp.read()
with open(OUT, "wb") as fh:
    fh.write(data)
print(f"5. Downloaded: {OUT} ({len(data)} bytes)")

from docx import Document as DocxDocument
from docx.oxml.ns import qn

d = DocxDocument(OUT)
n_paras = len(d.paragraphs)
rtl = sum(
    1
    for p in d.paragraphs
    if p._p.find(qn("w:pPr")) is not None and p._p.find(qn("w:pPr")).find(qn("w:bidi")) is not None
)
full_text = "\n".join(p.text for p in d.paragraphs)
print(f"6. DOCX: paragraphs={n_paras}, RTL={rtl}, tables={len(d.tables)}")
print("--- sample translated paragraphs ---")
count = 0
for p in d.paragraphs:
    if p.text.strip() and any("\u0600" <= c <= "\u06FF" for c in p.text) and len(p.text) > 40:
        print("  AR:", p.text[:120])
        count += 1
        if count >= 5:
            break
# terminology check: dictionary terms must appear
expected_terms = ["الإعاقة البصرية", "التكنولوجيا المساعدة"]
for term in expected_terms:
    found = term in full_text
    print(f"7. terminology '{term}': {'FOUND' if found else 'MISSING'}")
assert rtl > 10 and any("\u0600" <= c <= "\u06FF" for c in full_text)
print("\nREAL API E2E: SUCCESS")
