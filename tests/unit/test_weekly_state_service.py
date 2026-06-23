"""Unit tests for WeeklyStateService.

Uses an in-memory stub store — zero AWS dependencies.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.services.weekly_state import WeeklyStateService


# ---------------------------------------------------------------------------
# In-memory stub — satisfies EventStore Protocol without any AWS
# ---------------------------------------------------------------------------


class InMemoryEventStore:
    """Minimal list-backed EventStore for testing."""

    def __init__(self, events: list[Event] | None = None) -> None:
        self._events: list[Event] = list(events or [])

    def append_event(self, event: Event) -> None:
        self._events.append(event)

    def list_events(self) -> list[Event]:
        return list(self._events)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monday_of(ref: date) -> date:
    """Return the Monday of the ISO week containing ``ref``."""
    return ref - timedelta(days=ref.weekday())


def _laundry(offset_days: int = 0, ref: date | None = None) -> Event:
    """Create a laundry_completed event on the Monday of the current week + offset_days."""
    base = ref or datetime.now(tz=UTC).date()
    monday = _monday_of(base)
    ts = datetime(monday.year, monday.month, monday.day, 12, 0, 0, tzinfo=UTC) + timedelta(
        days=offset_days
    )
    return Event(event_type=LAUNDRY_COMPLETED, timestamp=ts)


def _last_week_laundry() -> Event:
    """Create a laundry event dated to last Monday (previous ISO week)."""
    last_monday = _monday_of(datetime.now(tz=UTC).date()) - timedelta(weeks=1)
    ts = datetime(last_monday.year, last_monday.month, last_monday.day, 9, 0, 0, tzinfo=UTC)
    return Event(event_type=LAUNDRY_COMPLETED, timestamp=ts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestWeeklyStateServiceNoEvents:
    def test_laundry_count_is_zero(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore())
        summary = svc.get_summary()
        assert summary.laundry_count == 0

    def test_last_laundry_is_none(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore())
        assert svc.get_summary().last_laundry_timestamp is None

    def test_total_events_is_zero(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore())
        assert svc.get_summary().total_events == 0


@pytest.mark.unit()
class TestWeeklyStateServiceOneLaundry:
    def test_laundry_count_is_one(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore([_laundry()]))
        assert svc.get_summary().laundry_count == 1

    def test_last_laundry_timestamp_set(self) -> None:
        event = _laundry()
        svc = WeeklyStateService(InMemoryEventStore([event]))
        assert svc.get_summary().last_laundry_timestamp == event.timestamp

    def test_total_events_is_one(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore([_laundry()]))
        assert svc.get_summary().total_events == 1


@pytest.mark.unit()
class TestWeeklyStateServiceMultipleLaundry:
    def test_laundry_count_matches(self) -> None:
        events = [_laundry(0), _laundry(1), _laundry(2)]
        svc = WeeklyStateService(InMemoryEventStore(events))
        assert svc.get_summary().laundry_count == 3

    def test_last_laundry_is_most_recent(self) -> None:
        e1 = _laundry(0)
        e2 = _laundry(2)
        svc = WeeklyStateService(InMemoryEventStore([e1, e2]))
        assert svc.get_summary().last_laundry_timestamp == e2.timestamp

    def test_total_events_counts_all(self) -> None:
        events = [_laundry(0), _laundry(1), _laundry(3)]
        svc = WeeklyStateService(InMemoryEventStore(events))
        assert svc.get_summary().total_events == 3


@pytest.mark.unit()
class TestWeeklyStateServiceWeekFiltering:
    def test_last_week_event_excluded(self) -> None:
        events = [_last_week_laundry(), _laundry(0)]
        svc = WeeklyStateService(InMemoryEventStore(events))
        summary = svc.get_summary()
        assert summary.laundry_count == 1
        assert summary.total_events == 1

    def test_only_last_week_events_gives_zero(self) -> None:
        svc = WeeklyStateService(InMemoryEventStore([_last_week_laundry()]))
        summary = svc.get_summary()
        assert summary.laundry_count == 0
        assert summary.total_events == 0

    def test_reference_date_respected(self) -> None:
        """Passing an explicit reference_date scopes the week correctly."""
        specific_date = date(2026, 6, 23)  # known Tuesday
        monday = _monday_of(specific_date)
        ts = datetime(monday.year, monday.month, monday.day, 8, 0, 0, tzinfo=UTC)
        event = Event(event_type=LAUNDRY_COMPLETED, timestamp=ts)

        svc = WeeklyStateService(InMemoryEventStore([event]))
        summary = svc.get_summary(reference_date=specific_date)
        assert summary.laundry_count == 1

    def test_sunday_event_included_in_same_week(self) -> None:
        """A Sunday event must count in the same week as that week's Monday."""
        sunday_event = _laundry(offset_days=6)
        svc = WeeklyStateService(InMemoryEventStore([sunday_event]))
        assert svc.get_summary().laundry_count == 1
