"""Unit tests for the wired schedule_handler.

Uses all five stubs — zero AWS, zero network. Covers both event types
(DailyPlanning / MorningReminder), recommended and not-recommended paths,
and the handler's response shape.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from hrse.handlers.schedule_handler import handler
from hrse.models.pricing import PricePoint
from hrse.models.weather import DailyForecast
from hrse.telegram.client import TelegramClientProtocol

# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _StubOctopus:
    """Returns a fixed list of cheap prices for any date range."""

    def __init__(self, prices: list[PricePoint]) -> None:
        self._prices = prices

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        return list(self._prices)


class _StubWeather:
    """Returns a fixed forecast for any date."""

    def __init__(self, forecast: DailyForecast) -> None:
        self._forecast = forecast

    def get_forecast(self, target_date: date) -> DailyForecast:
        return self._forecast


class _StubStore:
    """Returns an empty event list — no laundry runs recorded."""

    def append_event(self, event: Any) -> None:  # noqa: ANN401
        pass

    def list_events(self) -> list[Any]:
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SLOT = timedelta(minutes=30)


def _cheap_prices(target: date) -> list[PricePoint]:
    """Four cheap contiguous afternoon slots on the target date."""
    base = datetime(target.year, target.month, target.day, 13, 0, tzinfo=UTC)
    return [PricePoint(timestamp=base + i * _SLOT, price_pence=7.0) for i in range(4)]


def _good_forecast(target: date) -> DailyForecast:
    return DailyForecast(
        forecast_date=target,
        temperature_max=22.0,
        uv_index=6.0,
        rain_probability=15,
    )


def _bad_forecast(target: date) -> DailyForecast:
    """Rainy, low-UV day — decision engine will decline."""
    return DailyForecast(
        forecast_date=target,
        temperature_max=12.0,
        uv_index=1.0,
        rain_probability=90,
    )


def _invoke(
    detail_type: str = "DailyPlanning",
    prices: list[PricePoint] | None = None,
    forecast: DailyForecast | None = None,
) -> tuple[dict[str, Any], MagicMock]:
    """Invoke the handler with stubs; return (response, mock_telegram)."""
    tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
    today = datetime.now(tz=UTC).date()
    target = today if detail_type == "MorningReminder" else tomorrow

    _prices = prices if prices is not None else _cheap_prices(target)
    _forecast = forecast if forecast is not None else _good_forecast(target)

    mock_telegram = MagicMock(spec=TelegramClientProtocol)

    response = handler(
        event={"source": "hrse.scheduler", "detail-type": detail_type, "detail": {}},
        context=MagicMock(),
        _octopus=_StubOctopus(_prices),
        _weather=_StubWeather(_forecast),
        _store=_StubStore(),
        _telegram=mock_telegram,
        _chat_id=123456789,
    )
    return response, mock_telegram


# ---------------------------------------------------------------------------
# DailyPlanning
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestDailyPlanning:
    def test_returns_200(self) -> None:
        response, _ = _invoke("DailyPlanning")
        assert response["statusCode"] == 200

    def test_body_is_valid_json(self) -> None:
        response, _ = _invoke("DailyPlanning")
        body = json.loads(response["body"])
        assert "recommended" in body
        assert "kind" in body
        assert "date" in body

    def test_kind_is_planning(self) -> None:
        response, _ = _invoke("DailyPlanning")
        assert json.loads(response["body"])["kind"] == "planning"

    def test_recommended_sends_telegram_message(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        mock_telegram.send_message.assert_called_once()
        _, kwargs = mock_telegram.send_message.call_args
        assert kwargs["chat_id"] == 123456789

    def test_recommended_message_contains_tomorrow(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        _, kwargs = mock_telegram.send_message.call_args
        assert "Tomorrow" in kwargs["text"]

    def test_recommended_message_contains_window(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        _, kwargs = mock_telegram.send_message.call_args
        assert "13:00" in kwargs["text"]

    def test_not_recommended_still_sends_message(self) -> None:
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        _, mock_telegram = _invoke("DailyPlanning", forecast=_bad_forecast(tomorrow))
        mock_telegram.send_message.assert_called_once()

    def test_not_recommended_body_flag(self) -> None:
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        response, _ = _invoke("DailyPlanning", forecast=_bad_forecast(tomorrow))
        assert json.loads(response["body"])["recommended"] is False


# ---------------------------------------------------------------------------
# MorningReminder
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestMorningReminder:
    def test_returns_200(self) -> None:
        response, _ = _invoke("MorningReminder")
        assert response["statusCode"] == 200

    def test_kind_is_reminder(self) -> None:
        response, _ = _invoke("MorningReminder")
        assert json.loads(response["body"])["kind"] == "reminder"

    def test_reminder_message_contains_header(self) -> None:
        _, mock_telegram = _invoke("MorningReminder")
        _, kwargs = mock_telegram.send_message.call_args
        assert "Reminder" in kwargs["text"]

    def test_recommended_reminder_prompts_laundry_done(self) -> None:
        _, mock_telegram = _invoke("MorningReminder")
        _, kwargs = mock_telegram.send_message.call_args
        assert "/laundry_done" in kwargs["text"]


# ---------------------------------------------------------------------------
# Default / fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestDefaultEventType:
    def test_unknown_detail_type_defaults_to_planning(self) -> None:
        response, _ = _invoke("UnknownType")
        assert json.loads(response["body"])["kind"] == "planning"
