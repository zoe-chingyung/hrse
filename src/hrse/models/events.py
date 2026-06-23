"""Domain models for household activity events and weekly summaries.

Sprint 2B — Event Memory Layer.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — used as Pydantic field type at runtime

from pydantic import BaseModel, ConfigDict, Field

from hrse.utils.datetime_utils import utcnow


class Event(BaseModel):
    """A single recorded household activity.

    Kept intentionally minimal: just the event type and when it happened.
    Additional metadata fields can be added in future sprints without
    breaking the stored JSON format (``extra="ignore"`` on load).
    """

    model_config = ConfigDict(extra="ignore")

    event_type: str = Field(..., min_length=1, description="Machine-readable activity identifier")
    timestamp: datetime = Field(
        default_factory=utcnow,
        description="UTC timestamp of when the activity was recorded",
    )


class WeeklySummary(BaseModel):
    """Aggregated view of household activity for the current ISO week.

    Week definition: Monday 00:00 UTC → Sunday 23:59 UTC.
    """

    model_config = ConfigDict(frozen=True)

    laundry_count: int = Field(ge=0, description="Number of laundry completions this week")
    last_laundry_timestamp: datetime | None = Field(
        None, description="Most recent laundry completion, or None if none this week"
    )
    total_events: int = Field(ge=0, description="Total events recorded this week")


# ---------------------------------------------------------------------------
# Event type constants — single source of truth, avoids raw strings in code
# ---------------------------------------------------------------------------

LAUNDRY_COMPLETED = "laundry_completed"
