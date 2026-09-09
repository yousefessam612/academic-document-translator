"""Filename sanitization and path-traversal prevention."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

# Extensions we accept; architecture allows adding more later.
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
# Planned extensions (rejected with a clear message until implemented)
PLANNED_EXTENSIONS = {".epub", ".pptx"}

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_NAME_LEN = 120


class UnsafeFilenameError(ValueError):
    pass


def sanitize_filename(filename: str | None) -> str:
    """Return a safe display filename. Raises UnsafeFilenameError for dangerous input."""
    if not filename:
        raise UnsafeFilenameError("Filename is required.")
    # Normalize unicode and strip any directory components the client may have sent.
    name = unicodedata.normalize("NFKC", filename)
    name = name.replace("\\", "/").split("/")[-1].strip()
    if not name or name in {".", ".."}:
        raise UnsafeFilenameError("Invalid filename.")
    if _UNSAFE_CHARS.search(name):
        # Replace unsafe characters rather than rejecting: display-only name.
        name = _UNSAFE_CHARS.sub("_", name)
    name = name.strip(". ")
    if not name:
        raise UnsafeFilenameError("Invalid filename.")
    if len(name) > _MAX_NAME_LEN:
        stem = name[: _MAX_NAME_LEN - 8]
        ext = Path(name).suffix[:7]
        name = stem + ext
    return name


def validate_extension(filename: str) -> str:
    """Validate the extension of the sanitized filename and return it (lowercase)."""
    ext = Path(filename).suffix.lower()
    if ext in ALLOWED_EXTENSIONS:
        return ext
    if ext in PLANNED_EXTENSIONS:
        raise UnsafeFilenameError(
            f"Files of type '{ext}' are not supported yet. "
            f"Supported types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )
    raise UnsafeFilenameError(
        f"Unsupported file type '{ext or '(none)'}'. "
        f"Supported types: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
    )


def resolve_within(base_dir: Path, relative: str | Path) -> Path:
    """Resolve a path and guarantee it stays inside base_dir (prevents traversal)."""
    candidate = (base_dir / relative).resolve()
    base = base_dir.resolve()
    if candidate != base and base not in candidate.parents:
        raise UnsafeFilenameError("Path traversal detected.")
    return candidate
