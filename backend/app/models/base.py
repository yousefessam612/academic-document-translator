from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Shared created_at / updated_at columns."""
