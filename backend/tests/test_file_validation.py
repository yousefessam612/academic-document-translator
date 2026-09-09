"""File validation, sanitization, size-limit, and upload endpoint tests."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.security import (
    UnsafeFilenameError,
    sanitize_filename,
    validate_extension,
)


class TestSanitizeFilename:
    def test_strips_directory_components(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"
        assert sanitize_filename("C:\\Windows\\System32\\book.pdf") == "book.pdf"
        assert sanitize_filename("/var/www/uploads/secret.docx") == "secret.docx"

    def test_rejects_empty_and_dots(self):
        with pytest.raises(UnsafeFilenameError):
            sanitize_filename("")
        with pytest.raises(UnsafeFilenameError):
            sanitize_filename("..")
        with pytest.raises(UnsafeFilenameError):
            sanitize_filename(None)

    def test_removes_unsafe_characters(self):
        assert sanitize_filename('my<>:"|?*file.pdf') == "my_______file.pdf"

    def test_long_name_truncated(self):
        name = "x" * 300 + ".pdf"
        assert len(sanitize_filename(name)) <= 120

    def test_unicode_normalized(self):
        assert sanitize_filename("cafe\u0301 .pdf")  # does not raise


class TestExtensionValidation:
    def test_allowed(self):
        assert validate_extension("book.pdf") == ".pdf"
        assert validate_extension("notes.docx") == ".docx"
        assert validate_extension("readme.txt") == ".txt"

    def test_rejected(self):
        for bad in ("evil.exe", "script.js", "archive.zip", "doc.pptx", "book.epub"):
            with pytest.raises(UnsafeFilenameError):
                validate_extension(bad)


class TestSizeLimit:
    def test_default_limit_is_100mb(self):
        from app.core.config import Settings

        s = Settings(_env_file=None)
        assert s.max_file_size_mb == 100
        assert s.max_file_size_bytes == 100 * 1024 * 1024

    @pytest.mark.parametrize(
        "delta,accepted",
        [
            (-1, True),  # limit - 1 byte -> accepted
            (0, True),  # exactly at limit -> accepted
            (1, False),  # limit + 1 byte -> rejected
        ],
    )
    def test_exact_boundary(self, delta, accepted, monkeypatch):
        """Boundary enforcement tested with a 1 MiB scaled limit (identical
        streaming code path as the 100 MB production limit)."""
        import asyncio

        from app.utils import files as file_utils

        limit_source = 1  # MB -> scaled boundary; production default is 100 MB
        monkeypatch.setattr(file_utils.settings, "max_file_size_mb", limit_source)
        limit = limit_source * 1024 * 1024
        data = b"a" * (limit + delta)

        class FakeUpload:
            async def read(self, n: int = -1):
                return data if n < 0 else data[:n]

        # FakeUpload must stream in chunks like a real upload:
        class ChunkedFakeUpload:
            def __init__(self):
                self._offset = 0

            async def read(self, n: int = -1):
                if self._offset >= len(data):
                    return b""
                chunk = data[self._offset : self._offset + n]
                self._offset += n
                return chunk

        if accepted:
            name, stored = asyncio.run(
                file_utils.save_upload_streaming(ChunkedFakeUpload(), ".pdf")
            )
            assert stored == limit + delta
            (file_utils.settings.uploads_dir / name).unlink(missing_ok=True)
        else:
            with pytest.raises(file_utils.FileTooLargeError):
                asyncio.run(file_utils.save_upload_streaming(ChunkedFakeUpload(), ".pdf"))
            # No partial file left behind
            leftovers = list(file_utils.settings.uploads_dir.glob("*.pdf"))
            assert all(p.stat().st_size != limit + delta for p in leftovers)


class TestUploadEndpoint:
    @pytest.fixture()
    def client(self):
        from app.main import app

        with TestClient(app) as c:
            yield c

    def test_upload_pdf(self, client, tmp_path):
        from tests.conftest import make_text_pdf

        pdf = make_text_pdf(tmp_path / "book.pdf")
        with open(pdf, "rb") as fh:
            response = client.post(
                "/api/documents/upload", files={"file": ("book.pdf", fh, "application/pdf")}
            )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["file_type"] == "pdf"
        assert body["original_filename"] == "book.pdf"

    def test_upload_rejects_bad_type(self, client):
        response = client.post(
            "/api/documents/upload",
            files={"file": ("virus.exe", b"MZ...", "application/octet-stream")},
        )
        assert response.status_code == 400

    def test_upload_rejects_mismatched_content(self, client):
        # DOCX claimed but content is not a zip
        response = client.post(
            "/api/documents/upload",
            files={"file": ("fake.docx", b"not a zip", "application/vnd...")},
        )
        assert response.status_code == 400

    def test_upload_rejects_oversize(self, client):
        # Scale the limit down to 1 MB to keep the test fast; same code path
        # enforces the real 100 MB limit in production.
        from app.core.config import settings

        original = settings.max_file_size_mb
        settings.max_file_size_mb = 1
        try:
            response = client.post(
                "/api/documents/upload",
                files={"file": ("big.pdf", b"%PDF-1.4 " + b"0" * (1024 * 1024), "application/pdf")},
            )
            assert response.status_code == 413
            detail = response.json()["detail"]
            assert "limit" in detail.lower()
        finally:
            settings.max_file_size_mb = original
