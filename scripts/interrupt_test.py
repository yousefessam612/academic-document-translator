"""Live interruption/resume test:

1. Upload the test PDF
2. Start translation (slow mock: 0.8s/chunk)
3. Wait until a few chunks complete
4. KILL the backend (simulated crash)
5. Restart the backend
6. Verify the job is 'paused' (recovered as interrupted)
7. Resume the job
8. Verify it completes and completed chunks were NOT re-translated
   (mock server request count check)
"""
import json
import subprocess
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api"
MOCK = "http://127.0.0.1:8787/v1"
PDF = r"C:\academic-translator\storage\temp\test_book.pdf"
PYTHON = r"C:\academic-translator\backend\.venv\Scripts\python.exe"
BACKEND_DIR = r"C:\academic-translator\backend"


def req(path, method="GET", data=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode() if data is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(r, timeout=60) as resp:
        if resp.status == 204:
            return None
        return json.loads(resp.read().decode())


def mock_stats():
    with urllib.request.urlopen(f"{MOCK}/_stats", timeout=10) as resp:
        return json.loads(resp.read().decode())


def upload():
    boundary = "----adtboundary"
    with open(PDF, "rb") as fh:
        file_bytes = fh.read()
    body = b"".join(
        [
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"Interruption_Book.pdf\"\r\nContent-Type: application/pdf\r\n\r\n".encode()
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
        return json.loads(resp.read().decode())


def start_backend():
    return subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BACKEND_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_backend(up=True, timeout=60):
    for _ in range(timeout * 2):
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=2) as resp:
                if up and resp.status == 200:
                    return True
        except Exception:
            if not up:
                return True
        time.sleep(0.5)
    return False


# 1. upload
doc = upload()
print(f"1. Uploaded doc {doc['id'][:8]}…")

# 2. start translation
job = req(
    f"/translation/{doc['id']}/start",
    method="POST",
    data={"settings": {"style": "Academic", "domain": "Visual Impairment", "chunk_target_chars": 400}},
)
job_id = job["id"]
print(f"2. Job started {job_id[:8]}…")

# 3. wait until >= 3 chunks completed
target = 3
for _ in range(120):
    p = req(f"/translation/jobs/{job_id}/progress")
    if p["completed_chunks"] >= target:
        break
    time.sleep(0.5)
p = req(f"/translation/jobs/{job_id}/progress")
requests_before_crash = mock_stats()["requests"]
print(f"3. Interrupting: completed={p['completed_chunks']}/{p['total_chunks']}, status={p['status']}")
assert p["completed_chunks"] >= 1, "no chunks completed before interruption"
completed_before = p["completed_chunks"]

# 4. kill backend (simulate crash)
import os

subprocess.run(
    ["powershell", "-Command",
     f"Get-CimInstance Win32_Process | Where-Object {{$_.CommandLine -like '*uvicorn app.main:app*'}} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"],
    capture_output=True,
)
time.sleep(2)
print(f"4. Backend killed (completed_before={completed_before}, mock requests={requests_before_crash})")

# 5. restart backend
proc = start_backend()
assert wait_backend(up=True), "backend did not restart"
print("5. Backend restarted")

# 6. verify job recovered as paused
p = req(f"/translation/jobs/{job_id}/progress")
print(f"6. After restart: status={p['status']}, completed={p['completed_chunks']}/{p['total_chunks']}")
assert p["status"] == "paused", f"expected paused, got {p['status']}"

# 7. resume
req(f"/translation/jobs/{job_id}/resume", method="POST")
final = None
for _ in range(240):
    time.sleep(1)
    p = req(f"/translation/jobs/{job_id}/progress")
    if p["status"] in ("completed", "failed", "cancelled"):
        final = p
        break
print(f"7. After resume: {final['status']} {final['completed_chunks']}/{final['total_chunks']}")
assert final["status"] == "completed", f"resume failed: {final['error_message']}"

# 8. completed chunks not re-translated
requests_after = mock_stats()["requests"]
expected_new = final["total_chunks"] - completed_before
actual_new = requests_after - requests_before_crash
print(
    f"8. Mock requests after resume: +{actual_new} (expected ≈ {expected_new} for remaining chunks)"
)
assert actual_new <= expected_new + 2, "completed chunks were re-translated!"

# 9. download works
with urllib.request.urlopen(f"{BASE}/documents/{doc['id']}/download/translated", timeout=60) as resp:
    data = resp.read()
print(f"9. Downloaded DOCX ({len(data)} bytes)")
assert len(data) > 1000

proc.terminate()
print("\nINTERRUPTION/RESUME TEST: SUCCESS")
