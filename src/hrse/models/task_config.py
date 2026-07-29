"""Configuration models for flexible household tasks.

Sprint 3  — LaundryTaskConfig (decision inputs).
Sprint 5C — FlexibleTaskConfig protocol + DishwasherConfig, EVChargingConfig.

Every concrete config is the user-defined constraint set the decision engine
evaluates against. Times are stored as ``HH:MM`` strings; the engine parses
them via ``hrse.utils.datetime_utils.parse_hhmm`` rather than relying on a
task-specific convenience property, which is what lets ``DecisionService``
stay generic across task types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hrse.utils.datetime_utils import parse_hhmm

if TYPE_CHECKING:
    from datetime import time

    from hrse.config import Settings
    from hrse.models.chat_settings import TaskProfile


@runtime_checkable
class FlexibleTaskConfig(Protocol):
    """Structural contract every flexible-task config satisfies.

    Captures exactly the fields ``DecisionService.evaluate`` reads. Any
    object with these attributes — ``LaundryTaskConfig``,
    ``DishwasherConfig``, ``EVChargingConfig``, or a future task type —
    can be passed to the engine without it knowing which concrete class it
    is. No inheritance required; this is checked structurally.
    """

    task_name: str
    target_runs_per_week: int
    duration_slots: int
    earliest_start: str
    latest_finish: str
    wash_budget_pence: float
    machine_kwh: float
    min_uv: float
    max_rain_probability: int


class _TaskConfigBase(BaseModel):
    """Shared HH:MM validation for every concrete flexible-task config.

    Subclasses declare their own fields (defaults differ per task type), but
    share this validation logic so it stays in exactly one place.
    """

    model_config = ConfigDict(frozen=True)

    @field_validator("earliest_start", "latest_finish", check_fields=False)
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        """Ensure time fields are valid HH:MM; stored as the original string."""
        parse_hhmm(value)  # raises if invalid
        return value

    @model_validator(mode="after")
    def _finish_after_start(self) -> _TaskConfigBase:
        """Ensure the window is non-empty: latest_finish must be after earliest_start."""
        if parse_hhmm(self.latest_finish) <= parse_hhmm(self.earliest_start):  # type: ignore[attr-defined]
            raise ValueError("latest_finish must be after earliest_start")
        return self


class LaundryTaskConfig(_TaskConfigBase):
    """User-defined constraints for the laundry task.

    Attributes:
        task_name:              Task identifier, always "laundry".
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

    task_name: str = Field(default="laundry", description="Task identifier")
    target_runs_per_week: int = Field(default=2, ge=1, description="Desired laundry runs per week")
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


class DishwasherConfig(_TaskConfigBase):
    """User-defined constraints for the dishwasher flexible task.

    Shorter than a laundry run and, unlike laundry, has no weather gate —
    a dishwasher runs indoors regardless of sun or rain (``min_uv=0``,
    ``max_rain_probability=100`` disable the weather rule entirely).
    """

    task_name: str = Field(default="dishwasher", description="Task identifier")
    target_runs_per_week: int = Field(
        default=5, ge=1, description="Desired dishwasher runs per week"
    )
    duration_slots: int = Field(default=3, ge=1, description="~1.5 hour cycle (3 x 30-min slots)")
    earliest_start: str = Field(default="08:00", description="Earliest start time, HH:MM")
    latest_finish: str = Field(default="22:00", description="Latest finish time, HH:MM")
    wash_budget_pence: float = Field(default=25.0, gt=0, description="Max spend per cycle in pence")
    machine_kwh: float = Field(default=1.0, gt=0, description="Energy per dishwasher cycle in kWh")
    min_uv: float = Field(default=0.0, ge=0, description="Unused — dishwashers run indoors")
    max_rain_probability: int = Field(
        default=100, ge=0, le=100, description="Unused — dishwashers run indoors"
    )


class EVChargingConfig(_TaskConfigBase):
    """User-defined constraints for the EV overnight-charging flexible task.

    A single charge session spans several hours and, like the dishwasher,
    has no weather gate — charging happens regardless of sun or rain.
    """

    task_name: str = Field(default="ev_charging", description="Task identifier")
    target_runs_per_week: int = Field(
        default=3, ge=1, description="Desired charge sessions per week"
    )
    duration_slots: int = Field(
        default=8, ge=1, description="4 hour charge session (8 x 30-min slots)"
    )
    earliest_start: str = Field(default="00:00", description="Earliest start time, HH:MM")
    latest_finish: str = Field(default="07:00", description="Latest finish time, HH:MM")
    wash_budget_pence: float = Field(
        default=200.0, gt=0, description="Max spend per charge session in pence"
    )
    machine_kwh: float = Field(
        default=7.0, gt=0, description="Energy per overnight charge session in kWh"
    )
    min_uv: float = Field(default=0.0, ge=0, description="Unused — no weather gate for charging")
    max_rain_probability: int = Field(
        default=100, ge=0, le=100, description="Unused — no weather gate for charging"
    )


# ---------------------------------------------------------------------------
# Task registry (Sprint 5C) — maps a ChatSettings.enabled_tasks key to its
# config class. Every value is default-constructible (Cls()) since none of
# their fields are required, which is what lets schedule_handler build a
# config for any enabled task without task-specific wiring.
# ---------------------------------------------------------------------------

TASK_REGISTRY: dict[str, type[FlexibleTaskConfig]] = {
    "laundry": LaundryTaskConfig,
    "dishwasher": DishwasherConfig,
    "ev": EVChargingConfig,
}
