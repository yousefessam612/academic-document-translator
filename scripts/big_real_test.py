"""BIG real-API test: >=10 pages, >=10,000 words, full translation."""
import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
PDF = r"C:\academic-translator\storage\temp\big_test_book.pdf"
OUT = r"C:\academic-translator\storage\temp\big_translated.docx"


def req(path, method="GET", data=None):
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(f"{BASE}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=180) as resp:
        if resp.status == 204:
            return None
        return json.loads(resp.read().decode())


# 0. wait for the user's retried job to finish first (shares the API concurrency)
print("waiting for existing job to settle...")
for _ in range(600):
    jobs = req("/translation/jobs")["jobs"]
    active = [j for j in jobs if j["status"] in ("translating", "queued", "analyzing", "chunking", "assembling")]
    if not active:
        break
    time.sleep(2)
for j in jobs[:5]:
    print(f"  existing job {j['id'][:8]}: {j['status']} {j['completed_chunks']}/{j['total_chunks']} failed={j['failed_chunks']}")
    if j.get("error_message"):
        print(f"    error: {j['error_message'][:200]}")

# 1. upload the big book
with open(PDF, "rb") as fh:
    file_bytes = fh.read()
boundary = "----adtboundary"
body = b"".join(
    [
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="Big_Academic_Book_20p.pdf"\r\nContent-Type: application/pdf\r\n\r\n'.encode()
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
with urllib.request.urlopen(r, timeout=180) as resp:
    doc = json.loads(resp.read().decode())
print(f"\n1. Uploaded {doc['original_filename']} ({doc['file_size']:,} bytes)")

# wait for auto-analysis
deadline = time.time() + 300
while time.time() < deadline:
    d = req(f"/documents/{doc['id']}")
    if d["status"] in ("analyzed", "analysis_failed"):
        break
    time.sleep(1)
a = d.get("analysis") or {}
print(
    f"2. Analyzed: pages={a.get('page_count')} chars={a.get('character_count'):,} "
    f"units={a.get('estimated_translation_units')} chunks={a.get('estimated_chunks')} "
    f"words~{a.get('character_count', 0) // 6:,}"
)
assert d["status"] == "analyzed", f"analysis failed: {a.get('error')}"
assert a["page_count"] >= 10 and a["character_count"] >= 55000, "test file not big enough"

# 3. start translation with default settings (like a real user)
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
        }
    },
)
job_id = job["id"]
print(f"3. Job {job_id[:8]} started — translating ~15k words with glm-5.3 (real API)")

# 4. monitor
start_time = time.time()
final = None
last = None
for i in range(1800):
    time.sleep(3)
    p = req(f"/translation/jobs/{job_id}/progress")
    marker = (p["status"], p["completed_chunks"], p["failed_chunks"])
    if marker != last:
        elapsed = int(time.time() - start_time)
        print(
            f"   {p['status']:11s} {p['progress_percentage']:5.1f}%  {p['completed_chunks']:>3}/{p['total_chunks']}"
            f" failed={p['failed_chunks']} chapter={(p['current_chapter'] or '-')[:38]} [{elapsed}s]"
        )
        last = marker
    if p["status"] in ("completed", "failed", "cancelled"):
        final = p
        break
assert final, "job did not finish"

if final["status"] != "completed":
    print("FAILED:", final["error_message"])
    for e in final["recent_errors"]:
        print("  ", e)
    raise SystemExit(1)

total_time = int(time.time() - start_time)

# 5. quality report
job = req(f"/translation/jobs/{job_id}")
qr = job["quality_report"]
print(f"\n5. Completed in {total_time}s ({total_time // 60}m{total_time % 60}s)")
print(
    f"   chunks: {qr['completed_chunks']}/{qr['total_chunks']} | empty: {qr['empty_translations']} "
    f"| consistent terms: {qr['terminology']['consistent_terms']} "
    f"| inconsistent: {len(qr['terminology']['inconsistent_terms'])}"
)

# 6. download + validate DOCX
with urllib.request.urlopen(f"{BASE}/documents/{doc['id']}/download/translated", timeout=180) as resp:
    data = resp.read()
with open(OUT, "wb") as fh:
    fh.write(data)
print(f"6. Downloaded {OUT} ({len(data):,} bytes)")

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
arabic_words = len([w for w in full_text.split() if any("\u0600" <= c <= "\u06FF" for c in w)])
headings = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
print(f"7. DOCX: paragraphs={n_paras} RTL={rtl} headings={len(headings)} arabic_words~{arabic_words:,}")
print("   sample headings:", headings[:3])

# 8. terminology consistency in the final document
for term in ["الإعاقة البصرية", "التكنولوجيا المساعدة", "محو أمية برايل", "التوجه والحركة"]:
    print(f"   term '{term}': {'FOUND' if term in full_text else 'missing'}")

# 9. usage
chunks = req(f"/translation/jobs/{job_id}/chunks", None) if False else None
import sys

sys.path.insert(0, r"C:\academic-translator\backend")
import os

os.chdir(r"C:\academic-translator\backend")
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.chunk import TranslationChunk as TC

with SessionLocal() as db:
    rows = list(db.scalars(select(TC).where(TC.job_id == job_id)))
    prompt = sum(c.prompt_tokens_used for c in rows)
    completion = sum(c.completion_tokens_used for c in rows)
    avg_attempts = sum(c.attempts for c in rows) / len(rows)
print(f"8. Usage: {prompt:,} prompt + {completion:,} completion tokens | avg attempts/chunk: {avg_attempts:.2f}")

assert rtl >= n_paras * 0.9
source_words = a["character_count"] / 6
assert arabic_words > 8000, f"expected 10k+ word translation, got {arabic_words}"
print(f"\nsource words ~{source_words:,.0f} -> arabic words {arabic_words:,}")
print("\nBIG REAL-API TEST: SUCCESS")
