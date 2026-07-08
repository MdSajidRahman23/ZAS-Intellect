from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naive UTC timestamp for SQLite/PostgreSQL DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
