"""Lambda handler for scheduled daily recommendation events.

Entry point: ``hrse.handlers.schedule_handler.handler``

Invocation path
---------------
EventBridge (cron) → Lambda

Two EventBridge rules invoke this handler daily:

* ``DailyPlanning``  (16:45 UTC) — fetches *tomorrow's* prices + weather,
  runs the decision engine, sends the planning notification.
* ``MorningReminder`` (08:00 UTC) — fetches *today's* prices + weather,
  re-runs the engine (Agile prices may have changed overnight), sends the
  reminder notification.

Event contract
--------------
EventBridge passes a ``detail-type`` field that the handler uses to determine
which notification kind to send and which date to target::

    {
        "source": "hrse.scheduler",
        "detail-type": "DailyPlanning" | "MorningReminder",
        "detail": {}
    }

Design
------
The handler is intentionally thin: validate input, resolve dependencies,
delegate to pure services, return. No business logic lives here.

Dependency injection
--------------------
``_octopus``, ``_weather``, ``_store``, ``_settings_store``, ``_telegram``,
and ``_chat_id`` are keyword-only parameters accepted for testing.
Production callers omit them; the handler resolves real instances from
LRU-cached factories.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from aws_lambda_powertools import Logger, Tracer

from hrse.clients.octopus import OctopusClientProtocol, get_octopus_client
from hrse.clients.weather import WeatherClientProtocol, get_weather_client
from hrse.config import get_settings
from hrse.models.chat_settings import ChatSettings
from hrse.models.task_config import TASK_REGISTRY, LaundryTaskConfig, build_task_config
from hrse.services.decision_engine import DecisionService
from hrse.services.notification import NotificationKind, NotificationService
from hrse.services.renderer import render_price_bar_chart
from hrse.services.weekly_state import WeeklyStateService
from hrse.store.chat_settings_store import ChatSettingsStore, get_chat_settings_store
from hrse.store.s3_store import get_event_store
from hrse.telegram.client import TelegramClientProtocol, get_telegram_client
from hrse.telegram.token_provider import get_chat_ids_provider

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext

    from hrse.models.recommendation import Recommendation
    from hrse.store.protocol import EventStore

logger = Logger()
tracer = Tracer()

_DETAIL_TYPE_PLANNING = "DailyPlanning"
_DETAIL_TYPE_REMINDER = "MorningReminder"


@logger.inject_lambda_context(log_event=True)
@tracer.capture_lambda_handler
def handler(
    event: dict[str, Any],
    context: LambdaContext,
    *,
    _octopus: OctopusClientProtocol | None = None,
    _weather: WeatherClientProtocol | None = None,
    _store: EventStore | None = None,
    _settings_store: ChatSettingsStore | None = None,
    _telegram: TelegramClientProtocol | None = None,
    _chat_id: int | None = None,
    _chat_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Fetch data, run the decision engine, send a Telegram notification.

    Args:
        event:           EventBridge invocation payload.
        context:         Lambda runtime context.
        _octopus:        Injected Octopus client (tests only).
        _weather:        Injected weather client (tests only).
        _store:          Injected event store (tests only).
        _settings_store: Injected chat settings store (tests only).
        _telegram:       Injected Telegram client (tests only).
        _chat_id:        Injected single chat ID (tests only, legacy).
        _chat_ids:       Injected chat ID list (tests only). Takes precedence
                         over ``_chat_id`` when both are supplied.

    Returns:
        A JSON-serialisable dict with ``statusCode`` and ``body``.
    """
    detail_type: str = event.get("detail-type", _DETAIL_TYPE_PLANNING)
    logger.info("Schedule handler invoked", extra={"detail_type": detail_type})

    # Resolve dependencies — use injected stubs in tests, real factories in prod.
    octopus = _octopus if _octopus is not None else get_octopus_client()
    weather = _weather if _weather is not None else get_weather_client()
    store = _store if _store is not None else get_event_store()
    settings_store = _settings_store if _settings_store is not None else get_chat_settings_store()
    telegram = _telegram if _telegram is not None else get_telegram_client()

    # Resolve target chat IDs.  _chat_ids > _chat_id > Secrets Manager.
    if _chat_ids is not None:
        chat_ids = _chat_ids
    elif _chat_id is not None:
        chat_ids = [_chat_id]
    else:
        chat_ids = get_chat_ids_provider()()

    # Determine target date and notification kind from the event.
    now = datetime.now(tz=UTC)
    if detail_type == _DETAIL_TYPE_REMINDER:
        target_date = now.date()
        kind = NotificationKind.REMINDER
    else:
        # Default: DailyPlanning — recommend for tomorrow.
        target_date = (now + timedelta(days=1)).date()
        kind = NotificationKind.PLANNING

    logger.info("Targeting date", extra={"date": target_date.isoformat(), "kind": kind.value})

    # Fetch prices for the full target day (00:00 → 00:00 next day UTC).
    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    prices = octopus.get_prices(day_start, day_end)
    logger.info("Fetched prices", extra={"count": len(prices)})

    # Fetch weather forecast for the target day.
    forecast = weather.get_forecast(target_date)
    logger.info(
        "Fetched forecast",
        extra={
            "uv": forecast.uv_index,
            "rain": forecast.rain_probability,
            "temp_max": forecast.temperature_max,
        },
    )

    # Load weekly summary from the event store.
    weekly_service = WeeklyStateService(store)
    summary = weekly_service.get_summary()
    logger.info("Weekly summary", extra={"laundry_count": summary.laundry_count})

    # Run the decision engine once using the household-wide global config.
    # This single laundry recommendation drives the response body / log
    # line below. The body intentionally stays a single flag rather than
    # growing a per-chat/per-task schema, since nothing currently consumes
    # it beyond logging/tests — each chat's *message* is built separately
    # below from its own enabled tasks and profile.
    global_settings = get_settings()
    recommendation = DecisionService().evaluate(
        summary=summary,
        prices=prices,
        forecast=forecast,
        config=LaundryTaskConfig.from_settings(global_settings),
    )
    logger.info(
        "Decision made",
        extra={"recommended": recommendation.recommended, "reasons": recommendation.reasons},
    )

    # Format and send a per-chat Telegram notification: one recommendation
    # per enabled task, honouring each task's own per-chat TaskProfile
    # (Sprint 5D) where one has been configured. Chats with no stored
    # settings default to ["laundry"], matching pre-5C behaviour exactly.
    for chat_id in chat_ids:
        chat_settings = _safe_get_chat_settings(settings_store, chat_id)
        profiles = chat_settings.profiles if chat_settings is not None else {}
        enabled_tasks = chat_settings.enabled_tasks if chat_settings is not None else ["laundry"]

        chat_recommendations: list[Recommendation] = []
        for task_name in enabled_tasks:
            if task_name not in TASK_REGISTRY:
                logger.warning(
                    "Unknown enabled task; skipping",
                    extra={"chat_id": chat_id, "task": task_name},
                )
                continue
            task_config = build_task_config(task_name, profiles.get(task_name), global_settings)
            chat_recommendations.append(
                DecisionService().evaluate(
                    summary=summary, prices=prices, forecast=forecast, config=task_config
                )
            )

        if not chat_recommendations:
            logger.warning("No valid enabled tasks; nothing to send", extra={"chat_id": chat_id})
            continue

        tz_name = chat_settings.effective_timezone if chat_settings is not None else None
        display_tz = ZoneInfo(tz_name or global_settings.display_timezone)
        message = NotificationService(display_tz=display_tz).format_multi(
            chat_recommendations, kind
        )

        # Bar chart is sent as its own MarkdownV2 message (ahead of the HTML
        # plan/reminder message) since Telegram can't mix parse modes within
        # one message. Sent first so mock/test assertions against "the last
        # call" keep referring to the plan message, matching pre-chart tests.
        if prices:
            chart_settings = (
                chat_settings
                if chat_settings is not None
                else ChatSettings(chat_id=chat_id, updated_at=now)
            )
            chart_text = render_price_bar_chart(prices, chart_settings)
            telegram.send_message(chat_id=chat_id, text=chart_text, parse_mode="MarkdownV2")

        telegram.send_message(chat_id=chat_id, text=message)
        logger.info("Notification sent", extra={"chat_id": chat_id, "tasks": enabled_tasks})

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "recommended": recommendation.recommended,
                "kind": kind.value,
                "date": target_date.isoformat(),
                "reasons": recommendation.reasons,
            }
        ),
    }


def _safe_get_chat_settings(store: ChatSettingsStore, chat_id: int) -> ChatSettings | None:
    """Fetch chat settings, tolerating store failures.

    A settings lookup failure must never block a notification from being
    sent — it just means that chat falls back to the global config.
    """
    try:
        return store.get(chat_id)
    except Exception:
        logger.exception(
            "Failed to load chat settings; using global defaults", extra={"chat_id": chat_id}
        )
        return None
