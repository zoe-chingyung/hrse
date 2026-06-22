"""Unit tests for datetime utilities."""

from __future__ import annotations

from datetime import UTC, datetime

from hrse.utils.datetime_utils import to_iso8601, utcnow


def test_utcnow_is_timezone_aware() -> None:
    dt = utcnow()
    assert dt.tzinfo is not None
    assert dt.tzinfo == UTC


def test_to_iso8601_format() -> None:
    dt = datetime(2025, 1, 15, 10, 30, 0, 123456, tzinfo=UTC)
    result = to_iso8601(dt)
    assert result == "2025-01-15T10:30:00.123Z"


def test_to_iso8601_ends_with_z() -> None:
    dt = utcnow()
    assert to_iso8601(dt).endswith("Z")
