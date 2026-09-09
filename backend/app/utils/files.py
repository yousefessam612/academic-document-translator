"""File utilities: streaming upload persistence, magic-byte sniffing, temp cleanup."""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import aiofiles

from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.security import ALLOWED_EXTENSIONS, UnsafeFilenameError, validate_extension

logger = get_logger(__name__)

MAGIC_SIGNATURES: list[tuple[str, bytes]] = [
    (".pdf", b"%PDF"),
    (".docx", b"PK\x03\x04"),
]


class FileTooLargeError(Exception):
    def __init__(self, size: int, limit: int):
        self.size = size
        self.limit = limit
        super().__init__(
            f"File exceeds the {settings.max_file_size_mb} MB limit "
            f"({size / (1024 * 1024):.2f} MB received, limit is {limit / (1024 * 1024):.2f} MB)."
        )


async def save_upload_streaming(file, extension: str) -> tuple[str, int]:
    """Stream an uploaded file to storage/uploads under a random internal name.

    Enforces the size limit while streaming, so a huge file is aborted early
    without ever being fully loaded into memory.

    Returns (stored_filename, size_bytes).
    """
    limit = settings.max_file_size_bytes
    stored_name = f"{uuid.uuid4().hex}{extension}"
    target: Path = settings.uploads_dir / stored_name
    size = 0
    try:
        async with aiofiles.open(target, "wb") as out:
            while True:
                block = await file.read(1024 * 1024)  # 1 MiB chunks
                if not block:
                    break
                size += len(block)
                if size > limit:
                    raise FileTooLargeError(size, limit)
                await out.write(block)
    except FileTooLargeError:
        target.unlink(missing_ok=True)
        raise
    except Exception:
        target.unlink(missing_ok=True)
        logger.error("Upload write failed", extra={"operation": "upload", "status": "error"})
        raise
    if size == 0:
        target.unlink(missing_ok=True)
        raise UnsafeFilenameError("Uploaded file is empty.")
    return stored_name, size


def sniff_extension(path: Path, claimed_ext: str) -> str | None:
    """Validate the file's magic bytes against its claimed extension.

    Returns the verified extension, or None if the content does not match
    any supported type. Text files carry no signature; they are validated
    by attempting a decode.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return None
    for ext, sig in MAGIC_SIGNATURES:
        if head.startswith(sig):
            return ext
    if claimed_ext == ".txt":
        # Try decoding as text (utf-8 then common single-byte encodings).
        try:
            raw = path.read_bytes()[:64 * 1024]
            raw.decode("utf-8")
            return ".txt"
        except UnicodeDecodeError:
            try:
                raw.decode("cp1256")
                return ".txt"
            except UnicodeDecodeError:
                return None
    return None


def verify_type(stored_path: Path, claimed_ext: str) -> str:
    """Verify the stored file actually matches the claimed type; raise otherwise."""
    verified = sniff_extension(stored_path, claimed_ext)
    if verified is None:
        raise UnsafeFilenameError(
            "File content does not match its type. The file may be corrupted "
            "or not a valid PDF/DOCX/TXT document."
        )
    if verified != claimed_ext:
        # e.g. user renamed .pdf to .docx
        raise UnsafeFilenameError(
            f"File content ({verified.strip('.')}) does not match the claimed "
            f"type ({claimed_ext.strip('.')})."
        )
    return verified


def unique_output_name(document_title: str) -> str:
    """Build a safe output filename for generated documents."""
    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in document_title).strip()
    safe = safe[:80] or "document"
    return f"{safe}_arabic.docx"


def cleanup_temp_files(max_age_hours: int | None = None) -> int:
    """Remove abandoned files from storage/temp older than the threshold.

    Uploads are NEVER touched (original documents are preserved permanently
    unless explicitly deleted by the user).
    """
    hours = max_age_hours if max_age_hours is not None else settings.temp_cleanup_hours
    cutoff = time.time() - hours * 3600
    removed = 0
    temp_dir = settings.temp_dir
    if not temp_dir.exists():
        return 0
    for item in temp_dir.iterdir():
        try:
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                removed += 1
        except OSError:  # pragma: no cover
            continue
    if removed:
        logger.info(
            f"Cleaned {removed} abandoned temp files",
            extra={"operation": "temp_cleanup", "status": "success", "count": removed},
        )
    return removed
