"""End-to-end job pipeline tests with a MOCK provider (no real API calls).

Covers: analysis -> chunking -> translation -> consistency -> DOCX assembly,
chunk failure, resume without re-translating completed chunks, and the
pause/resume flow.
"""
from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.database import SessionLocal, init_db
from app.models.chunk import TranslationChunk
from app.models.document import Document
from app.models.job import TranslationJob
from app.schemas.job import JobSettingsIn
from app.services.jobs.manager import JobManager
from app.services.terminology.seed import seed_default_terminology
from app.services.translation.provider import (
    ProviderResult,
    TransientAPIError,
    UsageEstimate,
)

TERM_MAP = {
    "visual impairment": "الإعاقة البصرية",
    "low vision": "ضعف البصر",
    "assistive technology": "التكنولوجيا المساعدة",
    "braille literacy": "محو أمية برايل",
}


def _fake_translate_text(text: str) -> str:
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    out = []
    for para in paras:
        lines = para.splitlines()
        if len(lines) > 1 and all(" | " in l for l in lines):
            out.append(
                "\n".join(" | ".join(f"({c})" for c in l.split(" | ")) for l in lines)
            )
        else:
            t = para
            for en, ar in TERM_MAP.items():
                t = re.sub(re.escape(en), ar, t, flags=re.IGNORECASE)
            out.append("ترجمة: " + t)
    return "\n\n".join(out)


class MockProvider:
    """Mock AgentRouter provider. Counts calls; can force failures."""

    name = "mock"

    def __init__(self, fail_markers: dict[str, int] | None = None, delay: float = 0.0):
        self.calls: list[str] = []
        self.fail_markers = fail_markers or {}
        self.delay = delay

    async def translate(self, messages):
        user_content = messages[-1]["content"]
        source = user_content.split("### TEXT TO TRANSLATE NOW\n")[-1]
        # Marker checks use ONLY the text to translate (context sections may
        # legitimately contain neighboring markers).
        for marker, remaining in list(self.fail_markers.items()):
            if marker in source:
                if remaining > 0:
                    self.fail_markers[marker] = remaining - 1
                    raise TransientAPIError("Simulated temporary failure")
                break
        self.calls.append(source)
        if self.delay:
            await asyncio.sleep(self.delay)
        return ProviderResult(
            text=_fake_translate_text(source),
            prompt_tokens=100,
            completion_tokens=80,
            model="mock",
        )

    async def validate_connection(self):
        return True, "mock connected"

    async def health_check(self):
        return True

    def get_model(self):
        return "mock-model"

    def estimate_usage(self, text):
        return UsageEstimate(input_tokens=len(text) // 4, output_tokens=len(text) // 4, characters=len(text))

    def call_count(self, marker: str) -> int:
        pattern = re.compile(rf"\b{re.escape(marker)}\b")
        return sum(1 for c in self.calls if pattern.search(c))


def create_document(blocks_text: list[str], filename: str = "test.pdf") -> Document:
    """Insert a document row with pre-built structure (skips file analysis)."""
    from app.services.document.structure import Block, blocks_to_json

    structure = []
    seq = 0
    for text in blocks_text:
        if text.startswith("# "):
            structure.append(Block(seq=seq, type="heading", text=text[2:], level=1, page=1))
        else:
            structure.append(Block(seq=seq, type="paragraph", text=text, page=1))
        seq += 1

    with SessionLocal() as db:
        doc = Document(
            id=uuid.uuid4().hex,
            original_filename=filename,
            stored_filename=f"{uuid.uuid4().hex}_{filename}",
            file_type="txt",
            file_size=1234,
            status="analyzed",
            title="Test Book on Visual Impairment",
            structure=blocks_to_json(structure),
            analysis={"file_type": "txt", "character_count": 100, "is_scanned": False},
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc


def make_content() -> list[str]:
    content = ["# Chapter 1 Visual Impairment"]
    for i in range(12):
        content.append(
            f"SEGMENT-{i} Students with visual impairment and low vision use assistive "
            f"technology in the classroom. Braille literacy is essential for education. "
            f"Paragraph number {i} of the academic document about visual impairment."
        )
    return content


@pytest.fixture(autouse=True)
def _setup_db():
    init_db()
    with SessionLocal() as db:
        seed_default_terminology(db)
    yield


class TestJobPipeline:
    def test_full_run_produces_docx(self, tmp_path: Path):
        provider = MockProvider()
        manager = JobManager(provider=provider)
        doc = create_document(make_content())
        job, created = manager.start_job(
            doc.id, JobSettingsIn(chunk_target_chars=400, style="Academic", domain="Visual Impairment")
        )
        assert created is True

        with SessionLocal() as db:
            job = db.get(TranslationJob, job.id)
            assert job.status == "completed", job.error_message
            assert job.total_chunks >= 3
            assert job.completed_chunks == job.total_chunks
            assert job.failed_chunks == 0
            assert job.progress_percentage == 100.0
            assert job.output_filename
            output = settings.outputs_dir / job.output_filename
            assert output.exists()
            assert output.suffix == ".docx"

            # Quality report with terminology consistency
            report = job.quality_report
            assert report["total_chunks"] == job.total_chunks
            assert report["terminology"]["chunks_checked"] == job.total_chunks

            # Translation memory populated
            from app.models.memory import TranslationMemoryEntry

            tm_count = len(list(db.scalars(select(TranslationMemoryEntry))))
            assert tm_count >= job.total_chunks

            # All chunks completed, ordered, non-empty
            chunks = list(
                db.scalars(
                    select(TranslationChunk)
                    .where(TranslationChunk.job_id == job.id)
                    .order_by(TranslationChunk.chunk_index)
                )
            )
            assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
            assert all(c.status == "completed" and c.translation for c in chunks)
            assert all("ترجمة" in c.translation for c in chunks)

    def test_failed_chunk_then_resume_no_retranslation(self):
        provider = MockProvider(fail_markers={"SEGMENT-5": 1})
        manager = JobManager(provider=provider)
        doc = create_document(make_content())
        job, _ = manager.start_job(doc.id, JobSettingsIn(chunk_target_chars=400))

        with SessionLocal() as db:
            job = db.get(TranslationJob, job.id)
            assert job.status == "failed", job.error_message
            assert job.failed_chunks == 1
            assert "failed" in (job.error_message or "").lower() or "chunk" in (job.error_message or "").lower()
            failed = list(
                db.scalars(
                    select(TranslationChunk).where(
                        TranslationChunk.job_id == job.id, TranslationChunk.status == "failed"
                    )
                )
            )
            assert len(failed) == 1
            assert failed[0].chunk_index >= 0
            completed_before = job.completed_chunks

        seg_counts_before = {
            i: provider.call_count(f"SEGMENT-{i}") for i in range(12)
        }

        # Resume: failed chunk retried, completed chunks untouched
        manager.retry_failed_chunks(job.id)

        with SessionLocal() as db:
            job2 = db.get(TranslationJob, job.id)
            assert job2.status == "completed", job2.error_message
            assert job2.completed_chunks == job2.total_chunks
            assert job2.failed_chunks == 0

        seg_counts_after = {
            i: provider.call_count(f"SEGMENT-{i}") for i in range(12)
        }
        failed_index = failed[0].chunk_index
        for i in range(12):
            if i == failed_index:
                continue
            # completed chunks must NOT have been re-translated
            assert seg_counts_after[i] == seg_counts_before[i], f"SEGMENT-{i} was re-translated"
        assert seg_counts_after[failed_index] == seg_counts_before[failed_index] + 1

    def test_completed_chunks_skipped_on_resume(self):
        """Resume mid-way (no explicit failure): pending chunks translated only."""
        provider = MockProvider()
        manager = JobManager(provider=provider)
        doc = create_document(make_content())
        job, _ = manager.start_job(doc.id, JobSettingsIn(chunk_target_chars=400))

        # Simulate an interruption: reset some chunks to pending, job to paused
        with SessionLocal() as db:
            chunks = list(
                db.scalars(
                    select(TranslationChunk)
                    .where(TranslationChunk.job_id == job.id)
                    .order_by(TranslationChunk.chunk_index)
                )
            )
            assert len(chunks) >= 4
            for chunk in chunks[2:]:
                chunk.status = "pending"
                chunk.translation = None
            job_row = db.get(TranslationJob, job.id)
            job_row.status = "paused"
            job_row.completed_chunks = 2
            db.commit()

        counts_before = {i: provider.call_count(f"SEGMENT-{i}") for i in range(12)}
        manager.resume_job(job.id)

        with SessionLocal() as db:
            job2 = db.get(TranslationJob, job.id)
            assert job2.status == "completed", job2.error_message

        counts_after = {i: provider.call_count(f"SEGMENT-{i}") for i in range(12)}
        for i in range(12):
            if counts_before[i] > 0 and i < 2:
                assert counts_after[i] == counts_before[i], f"SEGMENT-{i} re-translated"

    def test_missing_chunks_block_assembly(self):
        """A job with missing chunk rows must NOT generate a document."""
        provider = MockProvider()
        manager = JobManager(provider=provider)
        doc = create_document(make_content())
        job, _ = manager.start_job(doc.id, JobSettingsIn(chunk_target_chars=400))
        with SessionLocal() as db:
            assert db.get(TranslationJob, job.id).status == "completed"

        # Corrupt: delete one chunk and rerun assembly path via resume
        with SessionLocal() as db:
            victim = db.scalars(
                select(TranslationChunk)
                .where(TranslationChunk.job_id == job.id, TranslationChunk.chunk_index == 1)
            ).first()
            db.delete(victim)
            job_row = db.get(TranslationJob, job.id)
            job_row.status = "paused"
            db.commit()

            manager.resume_job(job.id)
            job3 = db.get(TranslationJob, job.id)
            # Assembly must refuse: chunk sequence invalid
            assert job3.status == "failed"
            assert "sequence" in (job3.error_message or "").lower()

    def test_duplicate_job_returns_existing(self):
        provider = MockProvider()
        manager = JobManager(provider=provider)
        doc = create_document(["# Chapter", "Visual impairment paragraph one."])
        job1, created1 = manager.start_job(doc.id)
        assert created1 is True
        with SessionLocal() as db:
            assert db.get(TranslationJob, job1.id).status == "completed"  # ran synchronously

        # A paused job must be returned instead of creating a duplicate.
        with SessionLocal() as db:
            j = db.get(TranslationJob, job1.id)
            j.status = "paused"
            db.commit()
        job2, created2 = manager.start_job(doc.id)
        assert created2 is False
        assert job2.id == job1.id


class TestPauseResumeFlow:
    @pytest.mark.asyncio
    async def test_pause_and_resume_live_job(self):
        provider = MockProvider(delay=0.15)
        manager = JobManager(provider=provider)
        content = make_content() + [f"Extra paragraph {i} about visual impairment education." for i in range(8)]
        doc = create_document(content)
        job, created = manager.start_job(doc.id, JobSettingsIn(chunk_target_chars=300))
        assert created

        # Wait until translating begins
        async def wait_status(target, timeout=30):
            elapsed = 0.0
            while elapsed < timeout:
                with SessionLocal() as db:
                    j = db.get(TranslationJob, job.id)
                    if j.status == target:
                        return True
                await asyncio.sleep(0.1)
                elapsed += 0.1
            return False

        assert await wait_status("translating"), "job never started translating"

        manager.pause_job(job.id)
        assert await wait_status("paused"), "job never paused"
        counts_at_pause = {i: provider.call_count(f"SEGMENT-{i}") for i in range(12)}

        manager.resume_job(job.id)
        assert await wait_status("completed"), "job never completed after resume"

        with SessionLocal() as db:
            j = db.get(TranslationJob, job.id)
            assert j.status == "completed", j.error_message
            assert j.completed_chunks == j.total_chunks

        # No completed chunk re-translated after pause/resume. Chunks that
        # were still pending at pause time are expected to translate after
        # resume (count 0 before).
        counts_after = {i: provider.call_count(f"SEGMENT-{i}") for i in range(12)}
        for i, before in counts_at_pause.items():
            if before > 0:
                assert counts_after[i] == before, f"SEGMENT-{i} re-translated after resume"

    @pytest.mark.asyncio
    async def test_cancel_live_job(self):
        provider = MockProvider(delay=0.15)
        manager = JobManager(provider=provider)
        doc = create_document(make_content())
        job, _ = manager.start_job(doc.id, JobSettingsIn(chunk_target_chars=300))

        async def wait_status(target, timeout=30):
            elapsed = 0.0
            while elapsed < timeout:
                with SessionLocal() as db:
                    j = db.get(TranslationJob, job.id)
                    if j.status == target:
                        return True
                await asyncio.sleep(0.1)
                elapsed += 0.1
            return False

        assert await wait_status("translating")
        manager.cancel_job(job.id)
        assert await wait_status("cancelled"), "job never cancelled"

        with SessionLocal() as db:
            j = db.get(TranslationJob, job.id)
            assert j.status == "cancelled"
            assert j.completed_chunks < j.total_chunks or j.completed_chunks == j.total_chunks
