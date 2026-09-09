"""Automatic post-upload analysis + analyze endpoint tests."""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.models.document import Document


def _wait_analyzed(client: TestClient, doc_id: str, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/documents/{doc_id}").json()
        if body["status"] in ("analyzed", "analysis_failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"analysis did not finish, last status={body['status']}")


class TestAutomaticAnalysis:
    @pytest.fixture()
    def client(self):
        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_pdf_analyzed_automatically_after_upload(self, client, tmp_path: Path):
        from tests.conftest import make_text_pdf

        pdf = make_text_pdf(tmp_path / "auto.pdf")
        with open(pdf, "rb") as fh:
            response = client.post(
                "/api/documents/upload",
                files={"file": ("auto.pdf", fh, "application/pdf")},
            )
        assert response.status_code == 201
        doc = _wait_analyzed(client, response.json()["id"])
        assert doc["status"] == "analyzed"
        assert doc["analysis"]["page_count"] == 3
        assert doc["analysis"]["has_extractable_text"] is True
        assert doc["analysis"]["estimated_chunks"] >= 1
        assert doc["title"]

    def test_docx_analyzed_automatically_after_upload(self, client, tmp_path: Path):
        from tests.conftest import make_docx

        docx = make_docx(tmp_path / "auto.docx")
        with open(docx, "rb") as fh:
            response = client.post(
                "/api/documents/upload",
                files={"file": ("auto.docx", fh, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            )
        assert response.status_code == 201
        doc = _wait_analyzed(client, response.json()["id"])
        assert doc["status"] == "analyzed"
        assert doc["analysis"]["table_count"] == 1
        assert doc["analysis"]["list_item_count"] == 3

    def test_manual_analyze_endpoint(self, client, tmp_path: Path):
        from tests.conftest import make_text_pdf

        pdf = make_text_pdf(tmp_path / "manual.pdf")
        with open(pdf, "rb") as fh:
            response = client.post(
                "/api/documents/upload",
                files={"file": ("manual.pdf", fh, "application/pdf")},
            )
        doc_id = response.json()["id"]
        _wait_analyzed(client, doc_id)

        # Re-analysis on demand succeeds.
        response = client.post(f"/api/documents/{doc_id}/analyze")
        assert response.status_code == 200
        doc = _wait_analyzed(client, doc_id)
        assert doc["status"] == "analyzed"

    def test_analyze_endpoint_404_for_unknown(self, client):
        response = client.post("/api/documents/nonexistent/analyze")
        assert response.status_code == 404

    def test_analysis_failure_recorded(self, client, db_session):
        """A document whose analysis fails gets status=analysis_failed + error."""
        from app.services.document.analysis_runner import run_analysis

        doc = Document(
            id="broken-doc",
            original_filename="missing.pdf",
            stored_filename="does_not_exist.pdf",
            file_type="pdf",
            file_size=10,
            status="uploaded",
        )
        db_session.add(doc)
        db_session.commit()

        import asyncio

        asyncio.run(run_analysis(doc.id))
        db_session.refresh(doc)
        assert doc.status == "analysis_failed"
        assert "missing" in (doc.analysis or {}).get("error", "").lower()
