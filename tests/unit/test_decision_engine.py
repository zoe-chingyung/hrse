"""Unit tests for DecisionService — the five-rule laundry engine.

Pure logic: plain constructed inputs, zero AWS, zero network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from hrse.models.events import WeeklySummary
from hrse.models.pricing import PricePoint
from hrse.models.task_config import LaundryTaskConfig
from hrse.models.weather import DailyForecast
from hrse.services.decision_engine import DecisionService

_SLOT = timedelta(minutes=30)
_DAY = date(2026, 6, 23)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _slots(start_hour: int, start_minute: int, prices: list[float]) -> list[PricePoint]:
    """Build contiguous 30-min PricePoints starting at the given UTC time."""
    base = datetime(_DAY.year, _DAY.month, _DAY.day, start_hour, start_minute, tzinfo=UTC)
    return [PricePoint(timestamp=base + i * _SLOT, price_pence=p) for i, p in enumerate(prices)]


def _summary(laundry_count: int) -> WeeklySummary:
    return WeeklySummary(
        laundry_count=laundry_count,
        last_laundry_timestamp=None,
        total_events=laundry_count,
    )


def _forecast(uv: float = 7.0, rain: int = 10) -> DailyForecast:
    return DailyForecast(
        forecast_date=_DAY, temperature_max=25.0, uv_index=uv, rain_probability=rain
    )


def _config(**overrides: object) -> LaundryTaskConfig:
    base: dict[str, object] = {
        "target_runs_per_week": 2,
        "duration_slots": 2,  # 1 hour, keeps fixtures short
        "earliest_start": "08:00",
        "latest_finish": "22:00",
        "max_price": 15.0,
        "min_uv": 5.0,
        "max_rain_probability": 20,
    }
    base.update(overrides)
    return LaundryTaskConfig(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Rule 1 — target met
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRule1TargetMet:
    def test_target_met_not_recommended(self) -> None:
        rec = DecisionService().evaluate(
            _summary(2), _slots(13, 0, [5.0, 5.0]), _forecast(), _config()
        )
        assert rec.recommended is False
        assert "target" in rec.reasons[0].lower()

    def test_target_exceeded_not_recommended(self) -> None:
        rec = DecisionService().evaluate(
            _summary(5), _slots(13, 0, [5.0, 5.0]), _forecast(), _config()
        )
        assert rec.recommended is False

    def test_target_not_met_continues(self) -> None:
        rec = DecisionService().evaluate(
            _summary(1), _slots(13, 0, [5.0, 5.0]), _forecast(), _config()
        )
        assert rec.recommended is True


# ---------------------------------------------------------------------------
# Rule 4 — weather gate
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRule4Weather:
    def test_rainy_day_not_recommended(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [5.0, 5.0]), _forecast(rain=50), _config()
        )
        assert rec.recommended is False
        assert any("rain" in r.lower() for r in rec.reasons)

    def test_low_uv_not_recommended(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [5.0, 5.0]), _forecast(uv=2.0), _config()
        )
        assert rec.recommended is False
        assert any("uv" in r.lower() for r in rec.reasons)

    def test_uv_exactly_at_threshold_fails(self) -> None:
        """min_uv is strict: uv == min_uv must fail."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [5.0, 5.0]), _forecast(uv=5.0), _config(min_uv=5.0)
        )
        assert rec.recommended is False

    def test_rain_exactly_at_threshold_fails(self) -> None:
        """max_rain_probability is strict: rain == max must fail."""
        rec = DecisionService().evaluate(
            _summary(0),
            _slots(13, 0, [5.0, 5.0]),
            _forecast(rain=20),
            _config(max_rain_probability=20),
        )
        assert rec.recommended is False

    def test_uv_just_above_threshold_passes(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [5.0, 5.0]), _forecast(uv=5.1), _config(min_uv=5.0)
        )
        assert rec.recommended is True


# ---------------------------------------------------------------------------
# Rule 2 — valid time windows
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRule2ValidWindows:
    def test_no_prices_not_recommended(self) -> None:
        rec = DecisionService().evaluate(_summary(0), [], _forecast(), _config())
        assert rec.recommended is False
        assert "window" in rec.reasons[0].lower()

    def test_window_outside_time_range_excluded(self) -> None:
        """Slots at 06:00 are before earliest_start 08:00."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(6, 0, [1.0, 1.0]), _forecast(), _config()
        )
        assert rec.recommended is False

    def test_window_ending_after_latest_finish_excluded(self) -> None:
        """A 2-slot run starting 21:30 would end 22:30, past latest_finish 22:00."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(21, 30, [1.0, 1.0]), _forecast(), _config()
        )
        assert rec.recommended is False

    def test_window_ending_exactly_at_latest_finish_allowed(self) -> None:
        """A run ending exactly at 22:00 is allowed (boundary inclusive)."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(21, 0, [1.0, 1.0]), _forecast(), _config()
        )
        assert rec.recommended is True
        assert rec.window is not None
        assert rec.window.end.hour == 22

    def test_non_contiguous_slots_do_not_form_window(self) -> None:
        """Two slots with a gap must not be treated as a valid 2-slot run."""
        s1 = PricePoint(timestamp=datetime(2026, 6, 23, 13, 0, tzinfo=UTC), price_pence=1.0)
        # Skip 13:30 — next slot is 14:00, leaving a gap.
        s2 = PricePoint(timestamp=datetime(2026, 6, 23, 14, 0, tzinfo=UTC), price_pence=1.0)
        rec = DecisionService().evaluate(_summary(0), [s1, s2], _forecast(), _config())
        assert rec.recommended is False


# ---------------------------------------------------------------------------
# Rule 3 — price filter
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRule3Price:
    def test_all_slots_above_threshold_not_recommended(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [20.0, 20.0]), _forecast(), _config(max_price=15.0)
        )
        assert rec.recommended is False
        assert any("threshold" in r.lower() for r in rec.reasons)

    def test_one_slot_above_threshold_disqualifies_window(self) -> None:
        """A window is only valid if EVERY slot is under the cap."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [5.0, 20.0]), _forecast(), _config(max_price=15.0)
        )
        assert rec.recommended is False

    def test_price_exactly_at_threshold_fails(self) -> None:
        """max_price is strict: price == max must fail."""
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [15.0, 15.0]), _forecast(), _config(max_price=15.0)
        )
        assert rec.recommended is False

    def test_price_just_below_threshold_passes(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [14.9, 14.9]), _forecast(), _config(max_price=15.0)
        )
        assert rec.recommended is True


# ---------------------------------------------------------------------------
# Rule 5 — ranking
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRule5Ranking:
    def test_picks_cheapest_window(self) -> None:
        # 08:00-09:00 costs 10+10=20; 13:00-14:00 costs 3+3=6 (cheaper).
        prices = _slots(8, 0, [10.0, 10.0]) + _slots(13, 0, [3.0, 3.0])
        rec = DecisionService().evaluate(_summary(0), prices, _forecast(), _config())
        assert rec.recommended is True
        assert rec.window is not None
        assert rec.window.start.hour == 13
        assert rec.expected_price_pence == 3.0

    def test_tie_broken_by_earliest_start(self) -> None:
        # Two windows both cost 8; the earlier (09:00) should win.
        prices = _slots(9, 0, [4.0, 4.0]) + _slots(15, 0, [4.0, 4.0])
        rec = DecisionService().evaluate(_summary(0), prices, _forecast(), _config())
        assert rec.recommended is True
        assert rec.window is not None
        assert rec.window.start.hour == 9

    def test_overlapping_windows_cheapest_subrun_chosen(self) -> None:
        # Four contiguous slots 13:00-15:00 priced 9,1,1,9.
        # Cheapest 2-slot run is the middle pair 13:30-14:30 (1+1=2).
        prices = _slots(13, 0, [9.0, 1.0, 1.0, 9.0])
        rec = DecisionService().evaluate(_summary(0), prices, _forecast(), _config())
        assert rec.recommended is True
        assert rec.window is not None
        assert rec.window.start.hour == 13
        assert rec.window.start.minute == 30
        assert rec.expected_price_pence == 1.0


# ---------------------------------------------------------------------------
# Happy path — full recommendation object
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHappyPath:
    def test_full_recommendation_shape(self) -> None:
        rec = DecisionService().evaluate(
            _summary(0), _slots(13, 0, [8.0, 8.8]), _forecast(uv=7.0, rain=10), _config()
        )
        assert rec.task == "laundry"
        assert rec.recommended is True
        assert rec.window is not None
        assert rec.window.start == datetime(2026, 6, 23, 13, 0, tzinfo=UTC)
        assert rec.window.end == datetime(2026, 6, 23, 14, 0, tzinfo=UTC)
        assert rec.expected_price_pence == 8.4  # (8.0 + 8.8) / 2
        assert len(rec.reasons) == 4

    def test_longer_duration_window(self) -> None:
        """duration_slots=4 yields a 2-hour window."""
        prices = _slots(13, 0, [5.0, 5.0, 5.0, 5.0])
        rec = DecisionService().evaluate(
            _summary(0), prices, _forecast(), _config(duration_slots=4)
        )
        assert rec.recommended is True
        assert rec.window is not None
        assert (rec.window.end - rec.window.start) == timedelta(hours=2)
