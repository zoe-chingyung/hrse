"""Unit tests for domain models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from hrse.models.schedule import (
    Resource,
    ResourceType,
    Schedule,
    ScheduleStatus,
    TimeWindow,
)


class TestTimeWindow:
    def _window(self, offset_hours: int = 1) -> TimeWindow:
        now = datetime.now(tz=UTC)
        return TimeWindow(start=now, end=now + timedelta(hours=offset_hours))

    def test_valid_window(self) -> None:
        w = self._window()
        assert w.end > w.start

    def test_end_before_start_raises(self) -> None:
        now = datetime.now(tz=UTC)
        with pytest.raises(ValidationError, match="end must be strictly after start"):
            TimeWindow(start=now, end=now - timedelta(seconds=1))

    def test_end_equal_start_raises(self) -> None:
        now = datetime.now(tz=UTC)
        with pytest.raises(ValidationError):
            TimeWindow(start=now, end=now)


class TestResource:
    def test_valid_resource(self) -> None:
        r = Resource(name="Washing Machine", resource_type=ResourceType.APPLIANCE)
        assert r.resource_type == ResourceType.APPLIANCE
        assert r.id  # auto-generated UUID

    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValidationError):
            Resource(name="", resource_type=ResourceType.APPLIANCE)

    def test_metadata_defaults_empty(self) -> None:
        r = Resource(name="Dryer", resource_type=ResourceType.APPLIANCE)
        assert r.metadata == {}


class TestSchedule:
    def _schedule(self) -> Schedule:
        now = datetime.now(tz=UTC)
        return Schedule(
            household_id="hh-001",
            window=TimeWindow(start=now, end=now + timedelta(hours=2)),
        )

    def test_default_status_is_pending(self) -> None:
        s = self._schedule()
        assert s.status == ScheduleStatus.PENDING

    def test_resources_default_empty(self) -> None:
        s = self._schedule()
        assert s.resources == []

    def test_auto_id(self) -> None:
        s1 = self._schedule()
        s2 = self._schedule()
        assert s1.id != s2.id

    def test_missing_household_id_raises(self) -> None:
        now = datetime.now(tz=UTC)
        with pytest.raises(ValidationError):
            Schedule(
                household_id="",
                window=TimeWindow(start=now, end=now + timedelta(hours=1)),
            )
