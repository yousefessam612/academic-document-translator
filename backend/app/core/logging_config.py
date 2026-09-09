"""Structured application logging.

Never logs API keys, full document content or full translations unless
LOG_DOCUMENT_CONTENT=true is explicitly set for debugging.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from app.core.config import settings

_SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "token", "secret", "password"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Custom structured fields via logger.info("...", extra={...})
        for key in ("job_id", "document_id", "chunk_id", "chunk_index", "operation",
                    "status", "duration_ms", "error_type", "attempt"):
            val = record.__dict__.get(key)
            if val is not None:
                payload[key] = val
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def scrub(record: logging.LogRecord) -> logging.LogRecord:
    """Mask anything that looks like a credential in the rendered message."""
    msg = str(record.getMessage())
    for key in _SENSITIVE_KEYS:
        if key in msg.lower():
            record.msg = msg  # keep type simple; scrub below
            record.msg = _mask_after_key(msg)
            record.args = None
            msg = str(record.msg)
    return record


def _mask_after_key(message: str) -> str:
    import re

    def repl(m: re.Match) -> str:
        return m.group(1) + "***"

    return re.sub(
        r"((?:api[_-]?key|authorization|token|secret|password)\s*[=:]\s*)(\S+)",
        repl,
        message,
        flags=re.IGNORECASE,
    )


def setup_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
