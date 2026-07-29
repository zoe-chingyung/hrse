"""Unit tests for LaundryTaskConfig, including Sprint 5A's from_settings mapping."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hrse.config import Settings
from hrse.models.chat_settings import TaskProfile
from hrse.models.task_config import LaundryTaskConfig

# ---------------------------------------------------------------------------
# Existing validation behaviour
# ---------------------------------------------------------------------------


class TestLaundryTaskConfigValidation:
    def test_valid_hhmm_accepted(self) -> None:
        config = LaundryTaskConfig(target_runs_per_week=2, earliest_start="08:00")
        assert config.earliest_start_time.hour == 8

    def test_invalid_hhmm_rejected(self) -> None:
        with pytest.raises(ValidationError, match="HH:MM"):
            LaundryTaskConfig(target_runs_per_week=2, earliest_start="not-a-time")

    def test_out_of_range_hhmm_rejected(self) -> None:
        with pytest.raises(ValidationError, match="out of range"):
            LaundryTaskConfig(target_runs_per_week=2, earliest_start="25:00")

    def test_finish_before_start_rejected(self) -> None:
        with pytest.raises(ValidationError, match="latest_finish must be after earliest_start"):
            LaundryTaskConfig(target_runs_per_week=2, earliest_start="20:00", latest_finish="08:00")


# ---------------------------------------------------------------------------
# from_settings — Sprint 5A
# ---------------------------------------------------------------------------


class TestFromSettings:
    def test_maps_every_field(self) -> None:
        settings = Settings(
            laundry_target_per_week=3,
            duration_slots=6,
            earliest_start="07:30",
            latest_finish="21:00",
            wash_budget_pence=55.0,
            machine_kwh=2.0,
            min_uv=2.5,
            max_rain_probability=60,
        )
        config = LaundryTaskConfig.from_settings(settings)

        assert config.target_runs_per_week == 3
        assert config.duration_slots == 6
        assert config.earliest_start == "07:30"
        assert config.latest_finish == "21:00"
        assert config.wash_budget_pence == 55.0
        assert config.machine_kwh == 2.0
        assert config.min_uv == 2.5
        assert config.max_rain_probability == 60

    def test_defaults_match_previous_hardcoded_values(self) -> None:
        # Regression guard: these were the literal values in the deleted
        # schedule_handler._DEFAULT_CONFIG constant.
        config = LaundryTaskConfig.from_settings(Settings())

        assert config.target_runs_per_week == 2
        assert config.duration_slots == 4
        assert config.earliest_start == "08:00"
        assert config.latest_finish == "22:00"
        assert config.wash_budget_pence == 40.0
        assert config.machine_kwh == 1.5
        assert config.min_uv == 3.0
        assert config.max_rain_probability == 40

    def test_invalid_hhmm_env_value_raises_at_construction(self) -> None:
        settings = Settings(earliest_start="not-a-time")
        with pytest.raises(ValidationError, match="HH:MM"):
            LaundryTaskConfig.from_settings(settings)


# ---------------------------------------------------------------------------
# from_profile_or_settings — Sprint 5B precedence
# ---------------------------------------------------------------------------


class TestFromProfileOrSettings:
    def test_profile_absent_falls_back_to_settings(self) -> None:
        settings = Settings(laundry_target_per_week=3, wash_budget_pence=99.0)
        config = LaundryTaskConfig.from_profile_or_settings(None, settings)

        assert config.target_runs_per_week == 3
        assert config.wash_budget_pence == 99.0

    def test_profile_present_wins_over_settings(self) -> None:
        settings = Settings(laundry_target_per_week=3, wash_budget_pence=99.0)
        profile = TaskProfile(laundry_target_per_week=1, wash_budget_pence=25.0)
        config = LaundryTaskConfig.from_profile_or_settings(profile, settings)

        assert config.target_runs_per_week == 1
        assert config.wash_budget_pence == 25.0

    def test_profile_maps_every_shared_field(self) -> None:
        profile = TaskProfile(
            laundry_target_per_week=5,
            duration_slots=2,
            earliest_start="06:00",
            latest_finish="23:00",
            wash_budget_pence=15.0,
            machine_kwh=1.1,
            min_uv=1.0,
            max_rain_probability=80,
        )
        config = LaundryTaskConfig.from_profile_or_settings(profile, Settings())

        assert config.target_runs_per_week == 5
        assert config.duration_slots == 2
        assert config.earliest_start == "06:00"
        assert config.latest_finish == "23:00"
        assert config.wash_budget_pence == 15.0
        assert config.machine_kwh == 1.1
        assert config.min_uv == 1.0
        assert config.max_rain_probability == 80
