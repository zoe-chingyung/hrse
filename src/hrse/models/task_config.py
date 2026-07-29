"""Configuration model for the laundry flexible task.

Sprint 3 — Decision inputs.

Mirrors Section 9 of the requirements. This is the user-defined constraint
set the decision engine evaluates against. Times are stored as ``HH:MM``
strings and exposed as ``datetime.time`` via helper properties so the engine
never re-parses raw strings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hrse.utils.datetime_utils import parse_hhmm

if TYPE_CHECKING:
    from datetime import time

    from hrse.config import Settings
    from hrse.models.chat_settings import TaskProfile


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
        parse_hhmm(value)  # raises if invalid
        return value

    @model_validator(mode="after")
    def _finish_after_start(self) -> LaundryTaskConfig:
        """Ensure the window is non-empty: latest_finish must be after earliest_start."""
        if self.latest_finish_time <= self.earliest_start_time:
            raise ValueError("latest_finish must be after earliest_start")
        return self

    # ------------------------------------------------------------------
    # Construction from global Settings (Sprint 5A)
    # ------------------------------------------------------------------

    @classmethod
    def from_settings(cls, settings: Settings) -> LaundryTaskConfig:
        """Build a ``LaundryTaskConfig`` from environment-driven global ``Settings``.

        This is the single mapping between ``HRSE_*`` env vars and the
        engine's constraint model — keep it as the only place that reads
        laundry-related fields off ``Settings``.

        Args:
            settings: The application's global ``Settings`` instance.

        Returns:
            A validated ``LaundryTaskConfig`` built from the global defaults.
        """
        return cls(
            target_runs_per_week=settings.laundry_target_per_week,
            duration_slots=settings.duration_slots,
            earliest_start=settings.earliest_start,
            latest_finish=settings.latest_finish,
            wash_budget_pence=settings.wash_budget_pence,
            machine_kwh=settings.machine_kwh,
            min_uv=settings.min_uv,
            max_rain_probability=settings.max_rain_probability,
        )

    @classmethod
    def from_profile_or_settings(
        cls, profile: TaskProfile | None, settings: Settings
    ) -> LaundryTaskConfig:
        """Build a ``LaundryTaskConfig``, preferring a per-chat profile when set.

        This is the precedence chain introduced in Sprint 5B: a chat that has
        completed ``/setup`` gets its own thresholds; every other chat keeps
        using the global ``Settings`` defaults from Sprint 5A. It also unifies
        the ``duration_slots`` duplication between the price-chart env var and
        the per-chat profile — the profile wins whenever it is set.

        Args:
            profile:  The chat's ``TaskProfile``, or ``None`` if unconfigured.
            settings: The application's global ``Settings`` instance, used as
                      the fallback when no profile is set.

        Returns:
            A validated ``LaundryTaskConfig``.
        """
        if profile is None:
            return cls.from_settings(settings)
        return cls(
            target_runs_per_week=profile.laundry_target_per_week,
            duration_slots=profile.duration_slots,
            earliest_start=profile.earliest_start,
            latest_finish=profile.latest_finish,
            wash_budget_pence=profile.wash_budget_pence,
            machine_kwh=profile.machine_kwh,
            min_uv=profile.min_uv,
            max_rain_probability=profile.max_rain_probability,
        )

    # ------------------------------------------------------------------
    # Convenience accessors — parsed once, no raw-string handling downstream
    # ------------------------------------------------------------------

    @property
    def earliest_start_time(self) -> time:
        """``earliest_start`` parsed to a ``datetime.time``."""
        return parse_hhmm(self.earliest_start)

    @property
    def latest_finish_time(self) -> time:
        """``latest_finish`` parsed to a ``datetime.time``."""
        return parse_hhmm(self.latest_finish)
