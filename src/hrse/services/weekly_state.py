"""WeeklyStateService — aggregates events into a weekly summary.

This service contains all date-arithmetic and aggregation logic.
It has no AWS dependencies; it only talks to an ``EventStore`` Protocol.
This makes it fully testable with a simple in-memory stub.

Week definition
---------------
Monday 00:00:00 UTC (inclusive) → Sunday 23:59:59 UTC (inclusive).
Implemented as: events whose ``timestamp`` falls in the ISO calendar week
that contains today.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from aws_lambda_powertools import Logger

from hrse.models.events import LAUNDRY_COMPLETED, Event, WeeklySummary
from hrse.store.protocol import EventStore

logger = Logger(child=True)


class WeeklyStateService:
    """Builds a ``WeeklySummary`` from the events in an ``EventStore``.

    Args:
        store: Any object satisfying the ``EventStore`` Protocol.
    """

    def __init__(self, store: EventStore) -> None:
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_summary(self, reference_date: date | None = None) -> WeeklySummary:
        """Build a ``WeeklySummary`` for the ISO week containing ``reference_date``.

        Args:
            reference_date: The date whose ISO week to summarise.
                            Defaults to today (UTC) when not supplied.

        Returns:
            A ``WeeklySummary`` with counts and the latest laundry timestamp.
        """
        ref = reference_date or datetime.now(tz=UTC).date()
        week_start, week_end = _iso_week_bounds(ref)

        all_events = self._store.list_events()
        week_events = [e for e in all_events if _in_week(e, week_start, week_end)]

        laundry_events = [e for e in week_events if e.event_type == LAUNDRY_COMPLETED]
        last_laundry = max((e.timestamp for e in laundry_events), default=None)

        logger.debug(
            "Weekly summary calculated",
            extra={
                "week_start": week_start.isoformat(),
                "total_events": len(week_events),
                "laundry_count": len(laundry_events),
            },
        )

        return WeeklySummary(
            laundry_count=len(laundry_events),
            last_laundry_timestamp=last_laundry,
            total_events=len(week_events),
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _iso_week_bounds(ref: date) -> tuple[date, date]:
    """Return the Monday and Sunday of the ISO week containing ``ref``.

    Args:
        ref: Any date.

    Returns:
        (monday, sunday) — both inclusive.
    """
    monday = ref - timedelta(days=ref.weekday())  # weekday() == 0 for Monday
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _in_week(event: Event, week_start: date, week_end: date) -> bool:
    """Return True if ``event.timestamp`` falls within [week_start, week_end] (UTC)."""
    event_date = event.timestamp.astimezone(UTC).date()
    return week_start <= event_date <= week_end
