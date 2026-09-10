"""Remote worker API tests: auth, claim, result, validation retry."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.database import SessionLocal
from app.models.chunk import TranslationChunk
from app.models.job import TranslationJob
from tests.test_job_resume import MockProvider, create_document, make_content

WORKER_HEADERS = {"X-Worker-Key": "test-worker-key"}


@pytest.fixture()
def worker_env(monkeypatch):
    monkeypatch.setattr(settings, "worker_mode", True, raising=False)
    monkeypatch.setattr(settings, "worker_api_key", "test-worker-key", raising=False)
    yield
    monkeypatch.setattr(settings, "worker_mode", False, raising=False)
    monkeypatch.setattr(settings, "worker_api_key", "", raising=False)


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _seed_job(chunks_chars: int = 400) -> tuple[str, str]:
    """Create an analyzed document + job with pending chunks (worker mode)."""
    from app.schemas.job import JobSettingsIn
    from app.services.jobs.manager import JobManager

    doc = create_document(make_content())
    job_id = "workerjob0001"
    with SessionLocal() as db:
        job = TranslationJob(
            id=job_id,
            document_id=doc.id,
            status="translating",
            settings=JobSettingsIn(chunk_target_chars=chunks_chars).model_dump(),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        job_settings = dict(job.settings or {})

    manager = JobManager(provider=MockProvider())
    asyncio.run(manager._analyze_and_chunk(job_id, doc, job_settings))
    # mimic the pipeline's next step (worker mode: status stays "translating"
    # while the remote worker processes chunks)
    with SessionLocal() as db:
        job = db.get(TranslationJob, job_id)
        job.status = "translating"
        db.commit()
    return doc.id, job_id


class TestWorkerAuth:
    def test_disabled_when_worker_mode_off(self, client):
        response = client.get("/api/worker/status", headers=WORKER_HEADERS)
        assert response.status_code == 404

    def test_requires_worker_key(self, client, worker_env):
        response = client.get("/api/worker/status")
        assert response.status_code == 401
        response = client.get("/api/worker/status", headers={"X-Worker-Key": "wrong"})
        assert response.status_code == 401

    def test_status_with_key(self, client, worker_env):
        response = client.get("/api/worker/status", headers=WORKER_HEADERS)
        assert response.status_code == 200
        assert response.json()["mode"] == "worker"


class TestClaimAndResult:
    def test_claim_returns_tasks_with_messages(self, client, worker_env):
        _doc_id, job_id = _seed_job()
        response = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 2})
        assert response.status_code == 200
        body = response.json()
        assert len(body["tasks"]) == 2
        task = body["tasks"][0]
        assert task["messages"] and task["source_text"]
        assert "TEXT TO TRANSLATE NOW" in task["messages"][-1]["content"]
        # claimed chunks are marked translating
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, task["chunk_id"])
            assert chunk.status == "translating"
        # second claim skips them
        body2 = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 2}).json()
        assert all(t["chunk_id"] != task["chunk_id"] for t in body2["tasks"])

    def test_valid_result_completes_chunk(self, client, worker_env):
        _doc_id, job_id = _seed_job()
        task = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 1}).json()["tasks"][0]
        translation = "ترجمة: " + task["source_text"][: len(task["source_text"]) // 2]
        # ensure paragraphs count matches enough to pass validation
        src_paras = [p for p in task["source_text"].split("\n\n") if p.strip()]
        if len(src_paras) > 1:
            translation = "ترجمة: " + "\n\n".join(
                "نص عربي كامل ومفيد جداً للمحتوى الأكاديمي هنا." for _ in src_paras
            )
        response = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={
                "chunk_id": task["chunk_id"],
                "ok": True,
                "translation": translation,
                "prompt_tokens": 100,
                "completion_tokens": 80,
                "attempts_done": 1,
            },
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is True
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, task["chunk_id"])
            assert chunk.status == "completed"
            assert chunk.translation
            assert chunk.prompt_tokens_used == 100
            job = db.get(TranslationJob, job_id)
            assert job.completed_chunks == 1

    def test_invalid_result_returns_retry_messages(self, client, worker_env):
        _doc_id, job_id = _seed_job()
        task = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 1}).json()["tasks"][0]
        # obviously invalid: one word
        response = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={"chunk_id": task["chunk_id"], "ok": True, "translation": "قصير", "attempts_done": 1},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] is False
        assert body["retry_messages"], "must provide corrective retry messages"
        assert any("rejected" in m.get("content", "") for m in body["retry_messages"])
        # chunk not completed yet
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, task["chunk_id"])
            assert chunk.status == "translating"

    def test_retry_with_correction_accepted(self, client, worker_env):
        _doc_id, job_id = _seed_job()
        task = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 1}).json()["tasks"][0]
        bad = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={"chunk_id": task["chunk_id"], "ok": True, "translation": "قصير", "attempts_done": 1},
        ).json()
        # worker retries with the corrective messages and a good translation
        src_paras = [p for p in task["source_text"].split("\n\n") if p.strip()]
        good = "ترجمة: " + "\n\n".join("نص عربي كامل ومفيد جداً للمحتوى الأكاديمي." for _ in src_paras)
        response = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={
                "chunk_id": task["chunk_id"],
                "ok": True,
                "translation": good,
                "attempts_done": 2,
                "retry_messages": bad["retry_messages"],
            },
        )
        assert response.json()["accepted"] is True
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, task["chunk_id"])
            assert chunk.status == "completed"

    def test_worker_failure_marks_chunk_failed(self, client, worker_env):
        _doc_id, job_id = _seed_job()
        task = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 1}).json()["tasks"][0]
        response = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={"chunk_id": task["chunk_id"], "ok": False, "error": "provider quota exhausted"},
        )
        assert response.status_code == 200
        with SessionLocal() as db:
            chunk = db.get(TranslationChunk, task["chunk_id"])
            assert chunk.status == "failed"
            assert "quota" in (chunk.error_message or "")
            job = db.get(TranslationJob, job_id)
            assert job.failed_chunks == 1

    def test_result_for_unknown_chunk_404(self, client, worker_env):
        response = client.post(
            "/api/worker/result",
            headers=WORKER_HEADERS,
            json={"chunk_id": "nope", "ok": True, "translation": "x"},
        )
        assert response.status_code == 404


class TestWorkerModePipeline:
    def test_manager_waits_and_assembles_after_worker(self, client, worker_env):
        """Full worker-mode flow: job start -> claim all -> results -> job
        completes and the DOCX is produced."""
        from app.services.jobs.manager import JobHandle, JobManager

        _doc_id, job_id = _seed_job()
        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            job.status = "queued"
            db.commit()

        manager = JobManager(provider=MockProvider())

        async def drive():
            handle = JobHandle(job_id=job_id)
            task = asyncio.get_running_loop().create_task(manager._pipeline(job_id, handle))
            # act as the worker until the job completes
            deadline = time.time() + 120
            while time.time() < deadline:
                claim = client.post("/api/worker/claim", headers=WORKER_HEADERS, json={"limit": 4}).json()
                if not claim["tasks"]:
                    await asyncio.sleep(0.5)
                    with SessionLocal() as db:
                        j = db.get(TranslationJob, job_id)
                        if j.status in ("completed", "failed"):
                            break
                    continue
                for t in claim["tasks"]:
                    src_paras = [p for p in t["source_text"].split("\n\n") if p.strip()]
                    good = "ترجمة: " + "\n\n".join(
                        "نص عربي كامل ومفيد جداً للمحتوى الأكاديمي المهم هنا." for _ in src_paras
                    )
                    client.post(
                        "/api/worker/result",
                        headers=WORKER_HEADERS,
                        json={"chunk_id": t["chunk_id"], "ok": True, "translation": good, "attempts_done": 1},
                    )
            await asyncio.wait_for(task, timeout=60)

        asyncio.run(drive())

        with SessionLocal() as db:
            job = db.get(TranslationJob, job_id)
            assert job.status == "completed", job.error_message
            assert job.completed_chunks == job.total_chunks
            assert job.output_filename
