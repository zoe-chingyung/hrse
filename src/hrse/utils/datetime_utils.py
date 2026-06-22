"""Datetime helper utilities.

Keep all datetime handling UTC-aware and consistent across the codebase.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Prefer this over ``datetime.utcnow()`` which returns a naive datetime
    and is deprecated in Python 3.12.
    """
    return datetime.now(tz=UTC)


def to_iso8601(dt: datetime) -> str:
    """Serialise a datetime to an ISO-8601 string with 'Z' suffix."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
