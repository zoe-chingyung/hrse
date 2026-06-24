"""Unit tests for Sprint 3 decision models.

Pure Pydantic validation — zero AWS, zero network.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from hrse.models.pricing import PricePoint
from hrse.models.recommendation import Recommendation, RecommendationWindow
from hrse.models.task_config import LaundryTaskConfig
from hrse.models.weather import DailyForecast


@pytest.mark.unit()
class TestPricePoint:
    def test_accepts_positive_price(self) -> None:
        p = PricePoint(timestamp=datetime(2026, 6, 23, 13, 0, tzinfo=UTC), price_pence=8.4)
        assert p.price_pence == 8.4

    def test_accepts_negative_price(self) -> None:
        """Agile plunge pricing can go negative; this must be allowed."""
        p = PricePoint(timestamp=datetime(2026, 6, 23, 13, 0, tzinfo=UTC), price_pence=-2.1)
        assert p.price_pence == -2.1

    def test_is_frozen(self) -> None:
        p = PricePoint(timestamp=datetime(2026, 6, 23, 13, 0, tzinfo=UTC), price_pence=8.4)
        with pytest.raises(ValidationError):
            p.price_pence = 10.0  # type: ignore[misc]


@pytest.mark.unit()
class TestDailyForecast:
    def test_valid_forecast(self) -> None:
        f = DailyForecast(
            forecast_date=date(2026, 6, 23),
            temperature_max=27.0,
            uv_index=7.0,
            rain_probability=10,
        )
        assert f.uv_index == 7.0

    def test_rejects_rain_probability_above_100(self) -> None:
        with pytest.raises(ValidationError):
            DailyForecast(
                forecast_date=date(2026, 6, 23),
                temperature_max=27.0,
                uv_index=7.0,
                rain_probability=101,
            )

    def test_rejects_negative_uv(self) -> None:
        with pytest.raises(ValidationError):
            DailyForecast(
                forecast_date=date(2026, 6, 23),
                temperature_max=27.0,
                uv_index=-1.0,
                rain_probability=10,
            )


@pytest.mark.unit()
class TestLaundryTaskConfig:
    def test_minimal_valid_config(self) -> None:
        cfg = LaundryTaskConfig(target_runs_per_week=2)
        assert cfg.earliest_start == "08:00"
        assert cfg.latest_finish == "22:00"

    def test_time_properties_parse(self) -> None:
        cfg = LaundryTaskConfig(
            target_runs_per_week=2, earliest_start="09:30", latest_finish="21:15"
        )
        assert cfg.earliest_start_time.hour == 9
        assert cfg.earliest_start_time.minute == 30
        assert cfg.latest_finish_time.hour == 21

    def test_rejects_malformed_time(self) -> None:
        with pytest.raises(ValidationError):
            LaundryTaskConfig(target_runs_per_week=2, earliest_start="8am")

    def test_rejects_out_of_range_time(self) -> None:
        with pytest.raises(ValidationError):
            LaundryTaskConfig(target_runs_per_week=2, earliest_start="25:00")

    def test_rejects_finish_before_start(self) -> None:
        with pytest.raises(ValidationError):
            LaundryTaskConfig(
                target_runs_per_week=2,
                earliest_start="22:00",
                latest_finish="08:00",
            )

    def test_rejects_zero_target(self) -> None:
        with pytest.raises(ValidationError):
            LaundryTaskConfig(target_runs_per_week=0)

    def test_default_duration_is_four_slots(self) -> None:
        cfg = LaundryTaskConfig(target_runs_per_week=2)
        assert cfg.duration_slots == 4

    def test_rejects_zero_duration(self) -> None:
        with pytest.raises(ValidationError):
            LaundryTaskConfig(target_runs_per_week=2, duration_slots=0)


@pytest.mark.unit()
class TestRecommendationWindow:
    def test_valid_window(self) -> None:
        w = RecommendationWindow(
            start=datetime(2026, 6, 23, 13, 0, tzinfo=UTC),
            end=datetime(2026, 6, 23, 15, 0, tzinfo=UTC),
        )
        assert w.end > w.start

    def test_rejects_end_before_start(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationWindow(
                start=datetime(2026, 6, 23, 15, 0, tzinfo=UTC),
                end=datetime(2026, 6, 23, 13, 0, tzinfo=UTC),
            )

    def test_rejects_zero_length_window(self) -> None:
        ts = datetime(2026, 6, 23, 13, 0, tzinfo=UTC)
        with pytest.raises(ValidationError):
            RecommendationWindow(start=ts, end=ts)


@pytest.mark.unit()
class TestRecommendation:
    def test_not_recommended_has_no_window(self) -> None:
        rec = Recommendation(task="laundry", recommended=False, reasons=["target met"])
        assert rec.window is None
        assert rec.expected_price_pence is None

    def test_recommended_with_window(self) -> None:
        rec = Recommendation(
            task="laundry",
            recommended=True,
            window=RecommendationWindow(
                start=datetime(2026, 6, 23, 13, 0, tzinfo=UTC),
                end=datetime(2026, 6, 23, 15, 0, tzinfo=UTC),
            ),
            expected_price_pence=8.4,
            reasons=["cheap", "sunny"],
        )
        assert rec.recommended
        assert rec.expected_price_pence == 8.4
        assert len(rec.reasons) == 2
