"""Domain models for per-chat settings.

Sprint 6  — Group onboarding & language.
Sprint 5B — Per-chat task profile & onboarding state machine.
Sprint 5D — Per-task profiles (dict keyed by TASK_REGISTRY key, not a
            single laundry-only profile).

Each Telegram chat (private or group) can carry its own settings: display
language, a per-task-keyed dict of ``TaskProfile`` overrides, and the
transient state for an in-progress ``/setup`` conversation.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — used as Pydantic field type at runtime
from enum import StrEnum
from typing import Any
from zoneinfo import available_timezones

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from hrse.utils.datetime_utils import parse_hhmm


class Language(StrEnum):
    """Supported display languages.

    Values double as the suffix of the ``lang:*`` callback data sent by the
    onboarding inline keyboard.
    """

    EN = "en"
    ZH = "zh"


class TaskProfile(BaseModel):
    """Per-chat constraints for one task, set via the ``/setup`` conversation.

    Mirrors the ``FlexibleTaskConfig`` shape field-for-field (see
    ``build_task_config`` in ``models.task_config``) plus two extras
    collected during onboarding:

    * ``outdoor_drying`` — reserved for a future weather-gate refinement;
      collected now so the onboarding flow doesn't need a second pass later.
      Only meaningful for laundry; not asked for other tasks.
    * ``timezone`` — NOT part of the engine's constraint set. Consumed by
      the display layer (``handle_prices`` / ``NotificationService``) via
      ``ChatSettings.effective_timezone``, in preference to the global
      ``HRSE_DISPLAY_TIMEZONE``.
    """

    model_config = ConfigDict(frozen=True)

    target_per_week: int = Field(
        default=2,
        ge=1,
        validation_alias=AliasChoices("target_per_week", "laundry_target_per_week"),
        description="Desired runs per week for this task",
    )
    duration_slots: int = Field(
        default=4,
        ge=1,
        description="Length of one run as a count of consecutive 30-min slots (4 = 2 hours)",
    )
    earliest_start: str = Field(default="08:00", description="Earliest start time, HH:MM")
    latest_finish: str = Field(default="22:00", description="Latest finish time, HH:MM")
    wash_budget_pence: float = Field(default=40.0, gt=0, description="Max spend per run in pence")
    machine_kwh: float = Field(default=1.5, gt=0, description="Energy per run in kWh")
    min_uv: float = Field(default=3.0, ge=0, description="Lower UV threshold (laundry only)")
    max_rain_probability: int = Field(
        default=40, ge=0, le=100, description="Upper rain probability threshold, % (laundry only)"
    )
    outdoor_drying: bool = Field(default=True, description="Whether laundry dries outdoors")
    timezone: str | None = Field(
        default=None, description="IANA timezone for this chat's display, or None to use global"
    )

    @field_validator("earliest_start", "latest_finish")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        """Ensure time fields are valid HH:MM; stored as the original string."""
        parse_hhmm(value)  # raises if invalid
        return value

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str | None) -> str | None:
        """Ensure a supplied timezone is a real IANA zone name."""
        if value is not None and value not in available_timezones():
            raise ValueError(f"unknown IANA timezone, got {value!r}")
        return value

    @model_validator(mode="after")
    def _finish_after_start(self) -> TaskProfile:
        """Ensure the window is non-empty: latest_finish must be after earliest_start."""
        if parse_hhmm(self.latest_finish) <= parse_hhmm(self.earliest_start):
            raise ValueError("latest_finish must be after earliest_start")
        return self


class ChatSettings(BaseModel):
    """Settings for a single Telegram chat.

    Attributes:
        chat_id:         Telegram chat identifier. Negative for groups.
        language:        Display language for bot replies in this chat.
        profiles:        Per-task constraints, keyed by ``TASK_REGISTRY``
                         key (e.g. ``"laundry"``, ``"dishwasher"``, ``"ev"``
                         — NOT the config's ``task_name``, see
                         ``build_task_config``). A task with no entry here
                         uses the global ``Settings``/registry defaults.
        onboarding_step: Index of the current ``/setup`` question this chat
                         is answering, or None when no onboarding is active.
                         Transient — cleared once ``/setup`` completes.
        enabled_tasks:   Task registry keys (see
                         ``hrse.models.task_config.TASK_REGISTRY``) this chat
                         wants recommendations for. Defaults to
                         ``["laundry"]`` so pre-5C chats behave unchanged.
                         Managed via /tasks, /add_task, /remove_task.
        onboarding_complete: True once this chat has finished registration
                         (Sprint A: /start <code> then the /setup flow). Only
                         chats with this set are daily-notification recipients.
                         Forward-only field — pre-Sprint-A records lack it and
                         are treated as incomplete, not migrated.
        updated_at:      UTC timestamp of the last settings change.
    """

    model_config = ConfigDict(frozen=True)

    chat_id: int = Field(..., description="Telegram chat identifier (negative for groups)")
    language: Language = Field(default=Language.EN, description="Display language")
    profiles: dict[str, TaskProfile] = Field(
        default_factory=dict, description="Per-task constraints, keyed by TASK_REGISTRY key"
    )
    onboarding_step: int | None = Field(
        default=None, description="Current /setup question index, or None if not onboarding"
    )
    enabled_tasks: list[str] = Field(
        default_factory=lambda: ["laundry"],
        description="Task registry keys this chat gets recommendations for",
    )
    chart_green_threshold_pence: float = Field(
        default=10.0,
        ge=0,
        description="Bar-chart tier boundary: prices below this render as 🟢",
    )
    chart_red_threshold_pence: float = Field(
        default=20.0,
        ge=0,
        description="Bar-chart tier boundary: prices above this render as 🔴 (between is 🟡)",
    )
    chart_slot_limit: int = Field(
        default=8,
        ge=1,
        le=48,
        description="Max number of slots shown in the price bar chart notification",
    )
    chart_expensive_slot_limit: int = Field(
        default=8,
        ge=1,
        le=48,
        description="Max number of most-expensive slots shown in the avoid-list section of the price bar chart notification",
    )
    onboarding_complete: bool = Field(
        default=False,
        description="True once this chat has finished registration and is a notification recipient",
    )
    updated_at: datetime = Field(..., description="UTC timestamp of last update")

    @model_validator(mode="after")
    def _chart_thresholds_ordered(self) -> ChatSettings:
        """Ensure the red-tier boundary isn't below the green-tier one."""
        if self.chart_red_threshold_pence < self.chart_green_threshold_pence:
            raise ValueError("chart_red_threshold_pence must be >= chart_green_threshold_pence")
        return self

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_profile(cls, data: Any) -> Any:  # noqa: ANN401 — before-validator input
        """Migrate a legacy single ``profile`` key to ``profiles["laundry"]``.

        Pre-5D persisted JSON (and pre-5D code) used a single
        ``profile: TaskProfile | None`` field. Idempotent: if ``profiles``
        is already present, the input is assumed already migrated and
        passed through unchanged — this is what makes it safe to run on
        every load, not just once.
        """
        if not isinstance(data, dict):
            return data
        if "profiles" in data:
            return data
        data = dict(data)
        legacy_profile = data.pop("profile", None)
        data["profiles"] = {"laundry": legacy_profile} if legacy_profile is not None else {}
        return data

    @property
    def effective_timezone(self) -> str | None:
        """Return this chat's preferred display timezone, or None for the global default.

        NOTE (5D): timezone can be answered during any task's ``/setup``, so
        multiple profiles could each carry one. The laundry profile's
        timezone wins if set (the field's original home, from before
        per-task profiles existed); otherwise the first other profile
        (dict insertion order) with a timezone set is used.
        """
        laundry_profile = self.profiles.get("laundry")
        if laundry_profile is not None and laundry_profile.timezone:
            return laundry_profile.timezone
        for profile in self.profiles.values():
            if profile.timezone:
                return profile.timezone
        return None
