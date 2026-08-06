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
from hrse.models.chat_settings import ChatSettings, Language, TaskProfile
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


class _StubSettingsStore:
    """Returns no chat settings for any chat — global config defaults apply."""

    def __init__(self, settings: dict[int, ChatSettings] | None = None) -> None:
        self._settings = settings or {}

    def get(self, chat_id: int) -> ChatSettings | None:
        return self._settings.get(chat_id)

    def save(self, settings: ChatSettings) -> None:
        self._settings[settings.chat_id] = settings

    def list_all_chat_ids(self) -> list[int]:
        return list(self._settings.keys())


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
    settings_store: _StubSettingsStore | None = None,
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
        _settings_store=settings_store if settings_store is not None else _StubSettingsStore(),
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
        # One call for the price bar chart, one for the plan message.
        assert mock_telegram.send_message.call_count == 2
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
        assert mock_telegram.send_message.call_count == 2

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
class TestPriceBarChart:
    def test_chart_sent_before_plan_message_as_markdownv2(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        first_call, second_call = mock_telegram.send_message.call_args_list
        assert first_call.kwargs["parse_mode"] == "MarkdownV2"
        assert first_call.kwargs["text"].startswith("```\n")
        assert "parse_mode" not in second_call.kwargs or second_call.kwargs["parse_mode"] == "HTML"

    def test_chart_contains_a_price_row_for_each_slot(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        chart_text = mock_telegram.send_message.call_args_list[0].kwargs["text"]
        assert chart_text.count("▇") >= 4  # 4 cheap slots from _cheap_prices

    def test_daily_planning_chart_title_says_tomorrow(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning")
        chart_text = mock_telegram.send_message.call_args_list[0].kwargs["text"]
        assert "Tomorrow's prices" in chart_text

    def test_morning_reminder_chart_title_says_today(self) -> None:
        _, mock_telegram = _invoke("MorningReminder")
        chart_text = mock_telegram.send_message.call_args_list[0].kwargs["text"]
        assert "Today's prices" in chart_text

    def test_no_chart_sent_when_no_prices_available(self) -> None:
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        response, mock_telegram = _invoke(
            "DailyPlanning", prices=[], forecast=_bad_forecast(tomorrow)
        )
        assert response["statusCode"] == 200
        mock_telegram.send_message.assert_called_once()  # plan message only, no chart

    def test_chart_uses_stored_chat_language(self) -> None:
        # Regression test: a chat that persisted language=ZH must get a ZH
        # chart, proving the stored value (not a defaulted EN ChatSettings)
        # flows through to the renderer.
        settings_store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789, language=Language.ZH, updated_at=datetime.now(tz=UTC)
                )
            }
        )
        _, mock_telegram = _invoke("DailyPlanning", settings_store=settings_store)
        chart_text = mock_telegram.send_message.call_args_list[0].kwargs["text"]
        assert "聽日電價走勢" in chart_text

    def test_chart_defaults_to_english_when_no_settings_stored(self) -> None:
        _, mock_telegram = _invoke("DailyPlanning", settings_store=_StubSettingsStore())
        chart_text = mock_telegram.send_message.call_args_list[0].kwargs["text"]
        assert "Tomorrow's prices" in chart_text


@pytest.mark.unit()
class TestDefaultEventType:
    def test_unknown_detail_type_defaults_to_planning(self) -> None:
        response, _ = _invoke("UnknownType")
        assert json.loads(response["body"])["kind"] == "planning"


# ---------------------------------------------------------------------------
# Sprint 5A — env-driven config flows into the decision engine
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestEnvDrivenConfig:
    def test_wash_budget_env_var_flows_into_recommendation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Prices average 7.0p/kWh * 1.5kWh = 10.5p total. A budget of 1p
        # (well under that) must make the engine decline for every window,
        # proving the env var — not the deleted hardcoded default (40p) —
        # is what the handler actually uses.
        monkeypatch.setenv("HRSE_WASH_BUDGET_PENCE", "1")
        response, _ = _invoke("DailyPlanning")
        assert json.loads(response["body"])["recommended"] is False

    def test_max_rain_probability_env_var_flows_into_recommendation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # _good_forecast has 15% rain. Lowering the threshold below that
        # must make the weather gate reject it, proving the env var reaches
        # the engine rather than the deleted hardcoded default (40%).
        monkeypatch.setenv("HRSE_MAX_RAIN_PROBABILITY", "10")
        response, _ = _invoke("DailyPlanning")
        assert json.loads(response["body"])["recommended"] is False


# ---------------------------------------------------------------------------
# Sprint 5B — per-chat profile precedence in the notification loop
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestPerChatProfile:
    def test_chat_with_no_profile_uses_global_config(self) -> None:
        # No settings stored for chat 123456789 → falls back to global
        # Settings defaults, same as pre-5B behaviour.
        response, mock_telegram = _invoke("DailyPlanning")
        assert json.loads(response["body"])["recommended"] is True
        _, kwargs = mock_telegram.send_message.call_args
        assert "Tomorrow" in kwargs["text"]

    def test_chat_profile_wash_budget_overrides_global(self) -> None:
        # Prices are 7.0p/kWh; default machine_kwh 1.5 → 10.5p total. A
        # profile budget of 1p must decline for this chat even though the
        # global default budget (40p) would recommend it.
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    profiles={"laundry": TaskProfile(wash_budget_pence=1.0)},
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        _, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        _, kwargs = mock_telegram.send_message.call_args
        assert "not recommended" in kwargs["text"].lower()

    def test_chat_profile_timezone_overrides_global_display(self) -> None:
        # Global display_timezone defaults to Europe/London; a chat profile
        # with an Asia/Hong_Kong timezone should render its window in HKT.
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    profiles={"laundry": TaskProfile(timezone="Asia/Hong_Kong")},
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        _, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        _, kwargs = mock_telegram.send_message.call_args
        assert "HKT" in kwargs["text"]

    def test_settings_store_failure_falls_back_to_global_config(self) -> None:
        broken = MagicMock()
        broken.get.side_effect = RuntimeError("s3 down")
        response, mock_telegram = _invoke("DailyPlanning", settings_store=broken)
        assert json.loads(response["body"])["recommended"] is True
        assert mock_telegram.send_message.call_count == 2

    def test_legacy_single_profile_chat_settings_still_works(self) -> None:
        # Sprint 5D regression fixture: a chat whose ChatSettings was
        # constructed the pre-5D way (single `profile=` kwarg, migrated to
        # profiles["laundry"] by the before-validator) must behave
        # identically to one built with the new `profiles=` dict.
        legacy_settings = ChatSettings(
            chat_id=123456789,
            profile=TaskProfile(wash_budget_pence=1.0),
            updated_at=datetime.now(tz=UTC),
        )
        assert legacy_settings.profiles == {"laundry": TaskProfile(wash_budget_pence=1.0)}
        store = _StubSettingsStore({123456789: legacy_settings})
        _, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        _, kwargs = mock_telegram.send_message.call_args
        assert "not recommended" in kwargs["text"].lower()

    def test_dishwasher_only_chat_gets_dishwasher_recommendation(self) -> None:
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    enabled_tasks=["dishwasher"],
                    profiles={"dishwasher": TaskProfile(target_per_week=1)},
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        _, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        _, kwargs = mock_telegram.send_message.call_args
        assert "Dishwasher" not in kwargs["text"]  # single-task → no task label block
        assert "Tomorrow" in kwargs["text"]


# ---------------------------------------------------------------------------
# Sprint 5C — multi-task notifications via enabled_tasks / TASK_REGISTRY
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestMultiTaskNotifications:
    def test_default_enabled_tasks_produces_single_task_message(self) -> None:
        # No stored settings → enabled_tasks defaults to ["laundry"], so the
        # message must be the same single-block output as pre-5C.
        _, mock_telegram = _invoke("DailyPlanning")
        _, kwargs = mock_telegram.send_message.call_args
        assert "Dishwasher" not in kwargs["text"]
        assert "🏠 <b>Tomorrow's Energy Plan</b>" in kwargs["text"]

    def test_chat_with_two_enabled_tasks_gets_both_blocks(self) -> None:
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    enabled_tasks=["laundry", "dishwasher"],
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        _, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        _, kwargs = mock_telegram.send_message.call_args
        assert "Laundry" in kwargs["text"]
        assert "Dishwasher" in kwargs["text"]

    def test_unknown_enabled_task_is_skipped_not_fatal(self) -> None:
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    enabled_tasks=["laundry", "bogus_task"],
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        response, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        assert response["statusCode"] == 200
        assert mock_telegram.send_message.call_count == 2

    def test_all_enabled_tasks_unknown_sends_no_message(self) -> None:
        store = _StubSettingsStore(
            {
                123456789: ChatSettings(
                    chat_id=123456789,
                    enabled_tasks=["bogus_task"],
                    updated_at=datetime.now(tz=UTC),
                )
            }
        )
        response, mock_telegram = _invoke("DailyPlanning", settings_store=store)
        assert response["statusCode"] == 200
        mock_telegram.send_message.assert_not_called()


# ---------------------------------------------------------------------------
# Sprint A, Chunk 1 — recipient source flips from Secrets Manager to S3
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRecipientSourceFromStore:
    def test_fan_out_uses_store_chat_ids_when_no_injection_given(self) -> None:
        # No _chat_id / _chat_ids injected: the handler must fall back to
        # settings_store.list_all_chat_ids() rather than Secrets Manager.
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        store = _StubSettingsStore(
            {
                111: ChatSettings(chat_id=111, updated_at=datetime.now(tz=UTC)),
                222: ChatSettings(chat_id=222, updated_at=datetime.now(tz=UTC)),
            }
        )
        mock_telegram = MagicMock(spec=TelegramClientProtocol)
        response = handler(
            event={"source": "hrse.scheduler", "detail-type": "DailyPlanning", "detail": {}},
            context=MagicMock(),
            _octopus=_StubOctopus(_cheap_prices(tomorrow)),
            _weather=_StubWeather(_good_forecast(tomorrow)),
            _store=_StubStore(),
            _settings_store=store,
            _telegram=mock_telegram,
        )
        assert response["statusCode"] == 200
        notified_chat_ids = {
            call.kwargs["chat_id"] for call in mock_telegram.send_message.call_args_list
        }
        assert notified_chat_ids == {111, 222}

    def test_fan_out_empty_store_sends_nothing(self) -> None:
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        mock_telegram = MagicMock(spec=TelegramClientProtocol)
        response = handler(
            event={"source": "hrse.scheduler", "detail-type": "DailyPlanning", "detail": {}},
            context=MagicMock(),
            _octopus=_StubOctopus(_cheap_prices(tomorrow)),
            _weather=_StubWeather(_good_forecast(tomorrow)),
            _store=_StubStore(),
            _settings_store=_StubSettingsStore(),
            _telegram=mock_telegram,
        )
        assert response["statusCode"] == 200
        mock_telegram.send_message.assert_not_called()

    def test_injected_chat_ids_take_precedence_over_store(self) -> None:
        tomorrow = (datetime.now(tz=UTC) + timedelta(days=1)).date()
        store = _StubSettingsStore(
            {999: ChatSettings(chat_id=999, updated_at=datetime.now(tz=UTC))}
        )
        mock_telegram = MagicMock(spec=TelegramClientProtocol)
        response = handler(
            event={"source": "hrse.scheduler", "detail-type": "DailyPlanning", "detail": {}},
            context=MagicMock(),
            _octopus=_StubOctopus(_cheap_prices(tomorrow)),
            _weather=_StubWeather(_good_forecast(tomorrow)),
            _store=_StubStore(),
            _settings_store=store,
            _telegram=mock_telegram,
            _chat_ids=[42],
        )
        assert response["statusCode"] == 200
        notified_chat_ids = {
            call.kwargs["chat_id"] for call in mock_telegram.send_message.call_args_list
        }
        assert notified_chat_ids == {42}
