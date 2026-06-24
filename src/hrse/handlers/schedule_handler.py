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
``_octopus``, ``_weather``, ``_store``, ``_telegram``, and ``_chat_id``
are keyword-only parameters accepted for testing. Production callers omit
them; the handler resolves real instances from LRU-cached factories.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger, Tracer

from hrse.clients.octopus import OctopusClientProtocol, get_octopus_client
from hrse.clients.weather import WeatherClientProtocol, get_weather_client
from hrse.models.task_config import LaundryTaskConfig
from hrse.services.decision_engine import DecisionService
from hrse.services.notification import NotificationKind, NotificationService
from hrse.services.weekly_state import WeeklyStateService
from hrse.store.s3_store import get_event_store
from hrse.telegram.client import TelegramClientProtocol, get_telegram_client
from hrse.telegram.token_provider import get_chat_id_provider

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext

    from hrse.store.protocol import EventStore

logger = Logger()
tracer = Tracer()

# ---------------------------------------------------------------------------
# Default laundry config — will become config-driven in a future sprint
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = LaundryTaskConfig(
    target_runs_per_week=2,
    duration_slots=4,  # 4 x 30 min = 2-hour run
    earliest_start="08:00",
    latest_finish="22:00",
    wash_budget_pence=40.0,
    machine_kwh=1.5,
    min_uv=3.0,
    max_rain_probability=40,
)

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
    _telegram: TelegramClientProtocol | None = None,
    _chat_id: int | None = None,
) -> dict[str, Any]:
    """Fetch data, run the decision engine, send a Telegram notification.

    Args:
        event:    EventBridge invocation payload.
        context:  Lambda runtime context.
        _octopus: Injected Octopus client (tests only).
        _weather: Injected weather client (tests only).
        _store:   Injected event store (tests only).
        _telegram: Injected Telegram client (tests only).
        _chat_id: Injected chat ID (tests only).

    Returns:
        A JSON-serialisable dict with ``statusCode`` and ``body``.
    """
    detail_type: str = event.get("detail-type", _DETAIL_TYPE_PLANNING)
    logger.info("Schedule handler invoked", extra={"detail_type": detail_type})

    # Resolve dependencies — use injected stubs in tests, real factories in prod.
    octopus = _octopus if _octopus is not None else get_octopus_client()
    weather = _weather if _weather is not None else get_weather_client()
    store = _store if _store is not None else get_event_store()
    telegram = _telegram if _telegram is not None else get_telegram_client()
    chat_id = _chat_id if _chat_id is not None else get_chat_id_provider()()

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

    # Run the decision engine.
    recommendation = DecisionService().evaluate(
        summary=summary,
        prices=prices,
        forecast=forecast,
        config=_DEFAULT_CONFIG,
    )
    logger.info(
        "Decision made",
        extra={"recommended": recommendation.recommended, "reasons": recommendation.reasons},
    )

    # Format and send the Telegram notification.
    message = NotificationService().format(recommendation, kind)
    telegram.send_message(chat_id=chat_id, text=message)
    logger.info("Notification sent", extra={"chat_id": chat_id})

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
