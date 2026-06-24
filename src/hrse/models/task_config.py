"""Configuration model for the laundry flexible task.

Sprint 3 — Decision inputs.

Mirrors Section 9 of the requirements. This is the user-defined constraint
set the decision engine evaluates against. Times are stored as ``HH:MM``
strings and exposed as ``datetime.time`` via helper properties so the engine
never re-parses raw strings.
"""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _parse_hhmm(value: str) -> time:
    """Parse a strict ``HH:MM`` 24-hour string into a ``time``.

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


class LaundryTaskConfig(BaseModel):
    """User-defined constraints for the laundry task.

    Attributes:
        target_runs_per_week:   How many laundry runs the household wants per week.
        duration_slots:         Length of a single run as a count of consecutive
                                30-minute slots (4 = 2 hours).
        earliest_start:         Earliest acceptable start time, ``HH:MM`` (24h).
        latest_finish:          Latest acceptable finish time, ``HH:MM`` (24h).
        wash_budget_pence:      Maximum acceptable total spend per wash cycle in
                                pence. Engine recommends windows where
                                avg_price * machine_kwh < wash_budget_pence.
        machine_kwh:            Energy consumed per wash cycle in kWh (total,
                                not power draw). Typical range 1.0–2.0; default
                                1.5 kWh for a standard 40°C cotton cycle.
        min_uv:                 Only recommend slots when the day's UV index is
                                strictly above this value.
        max_rain_probability:   Only recommend slots when the day's rain
                                probability is strictly below this percentage.
    """

    model_config = ConfigDict(frozen=True)

    target_runs_per_week: int = Field(..., ge=1, description="Desired laundry runs per week")
    duration_slots: int = Field(
        default=4,
        ge=1,
        description="Length of one run as a count of consecutive 30-min slots (4 = 2 hours)",
    )
    earliest_start: str = Field(default="08:00", description="Earliest start time, HH:MM")
    latest_finish: str = Field(default="22:00", description="Latest finish time, HH:MM")
    wash_budget_pence: float = Field(
        default=40.0,
        gt=0,
        description="Max spend per wash cycle in pence (default 40p ≈ 40°C cotton wash)",
    )
    machine_kwh: float = Field(
        default=1.5,
        gt=0,
        description="Energy per wash cycle in kWh (1.0–2.0 typical; default 1.5)",
    )
    min_uv: float = Field(default=0.0, ge=0, description="Lower UV threshold")
    max_rain_probability: int = Field(
        default=100, ge=0, le=100, description="Upper rain probability threshold (percent)"
    )

    @field_validator("earliest_start", "latest_finish")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        """Ensure time fields are valid HH:MM; stored as the original string."""
        _parse_hhmm(value)  # raises if invalid
        return value

    @model_validator(mode="after")
    def _finish_after_start(self) -> LaundryTaskConfig:
        """Ensure the window is non-empty: latest_finish must be after earliest_start."""
        if self.latest_finish_time <= self.earliest_start_time:
            raise ValueError("latest_finish must be after earliest_start")
        return self

    # ------------------------------------------------------------------
    # Convenience accessors — parsed once, no raw-string handling downstream
    # ------------------------------------------------------------------

    @property
    def earliest_start_time(self) -> time:
        """``earliest_start`` parsed to a ``datetime.time``."""
        return _parse_hhmm(self.earliest_start)

    @property
    def latest_finish_time(self) -> time:
        """``latest_finish`` parsed to a ``datetime.time``."""
        return _parse_hhmm(self.latest_finish)
