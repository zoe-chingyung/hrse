"""Datetime helper utilities.

Keep all datetime handling UTC-aware and consistent across the codebase.
"""

from __future__ import annotations

from datetime import UTC, datetime, time


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime.

    Prefer this over ``datetime.utcnow()`` which returns a naive datetime
    and is deprecated in Python 3.12.
    """
    return datetime.now(tz=UTC)


def to_iso8601(dt: datetime) -> str:
    """Serialise a datetime to an ISO-8601 string with 'Z' suffix."""
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_hhmm(value: str) -> time:
    """Parse a strict ``HH:MM`` 24-hour string into a ``time``.

    Shared by every model that stores a user-facing clock time as a string
    (``LaundryTaskConfig``, ``TaskProfile``) so there is one parsing/error
    format to keep in sync.

    Args:
        value: A string like "08:00" or "22:30".

    Returns:
        The corresponding ``datetime.time``.

    Raises:
        ValueError: If the string is not valid ``HH:MM``.
    """
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError(f"time must be in HH:MM format, got {value!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise ValueError(f"time must be in HH:MM format, got {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"time out of range, got {value!r}")
    return time(hour=hour, minute=minute)
