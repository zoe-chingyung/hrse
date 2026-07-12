"""Telegram command handlers.

Each function receives the minimum context it needs and sends exactly one
reply (the language callback sends an acknowledgement plus one edit). No
business logic beyond formatting the reply text.

Sprint 2A: /health
Sprint 2B: /laundry_done, /events, /summary
Sprint 6 : /start welcome flow, /language, /prices, language callback
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger

from hrse import __version__
from hrse.clients.octopus import OctopusApiError
from hrse.i18n import MessageKey, bilingual_welcome, t
from hrse.models.chat_settings import ChatSettings, Language
from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.models.telegram import InlineKeyboardButton, InlineKeyboardMarkup
from hrse.services.price_chart import render_price_chart
from hrse.utils.datetime_utils import utcnow

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo

    from hrse.clients.octopus import OctopusClientProtocol
    from hrse.models.telegram import TelegramCallbackQuery
    from hrse.store.chat_settings_store import ChatSettingsStore
    from hrse.store.protocol import EventStore
    from hrse.telegram.client import TelegramClientProtocol

logger = Logger(child=True)

LANGUAGE_CALLBACK_PREFIX = "lang:"


# ---------------------------------------------------------------------------
# Sprint 2A
# ---------------------------------------------------------------------------


def handle_health(chat_id: int, client: TelegramClientProtocol, lang: Language) -> None:
    """Reply to the /health command with a simple status message."""
    client.send_message(chat_id=chat_id, text=t(MessageKey.HEALTH_OK, lang, version=__version__))


def handle_unknown(chat_id: int, text: str, client: TelegramClientProtocol, lang: Language) -> None:
    """Reply to any unrecognised command or plain text."""
    client.send_message(chat_id=chat_id, text=t(MessageKey.UNKNOWN_COMMAND, lang))


# ---------------------------------------------------------------------------
# Sprint 2B — event memory commands
# ---------------------------------------------------------------------------


def handle_laundry_done(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
    lang: Language,
) -> None:
    """Record a laundry completion event and confirm to the user.

    Creates an ``Event(event_type="laundry_completed")`` with the current
    UTC timestamp, persists it via the store, then replies with a
    confirmation that includes the running count for this week.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store to persist the new event.
        lang:    Display language for the reply.
    """
    from hrse.services.weekly_state import WeeklyStateService

    event = Event(event_type=LAUNDRY_COMPLETED, timestamp=utcnow())
    store.append_event(event)

    summary = WeeklyStateService(store).get_summary()
    client.send_message(
        chat_id=chat_id,
        text=t(MessageKey.LAUNDRY_RECORDED, lang, count=summary.laundry_count),
    )


def handle_events(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
    lang: Language,
) -> None:
    """Reply with up to 10 most recent events, newest first.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store to read events from.
        lang:    Display language for the reply.
    """
    events = store.list_events()
    recent = list(reversed(events))[:10]  # newest first, max 10

    if not recent:
        client.send_message(chat_id=chat_id, text=t(MessageKey.NO_EVENTS, lang))
        return

    lines = [t(MessageKey.RECENT_EVENTS_HEADER, lang)]
    for e in recent:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"  • {ts} — {e.event_type}")
    client.send_message(chat_id=chat_id, text="\n".join(lines))


def handle_summary(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
    lang: Language,
) -> None:
    """Reply with a weekly summary of household activity.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store used to build the summary.
        lang:    Display language for the reply.
    """
    from hrse.services.weekly_state import WeeklyStateService

    summary = WeeklyStateService(store).get_summary()

    last_laundry_str = (
        summary.last_laundry_timestamp.strftime("%Y-%m-%d")
        if summary.last_laundry_timestamp
        else "—"
    )

    client.send_message(
        chat_id=chat_id,
        text=t(
            MessageKey.WEEKLY_SUMMARY,
            lang,
            laundry_count=summary.laundry_count,
            last_laundry=last_laundry_str,
            total_events=summary.total_events,
        ),
    )


# ---------------------------------------------------------------------------
# Sprint 6 — onboarding, language, prices
# ---------------------------------------------------------------------------


def handle_welcome(chat_id: int, client: TelegramClientProtocol) -> None:
    """Send the bilingual onboarding message with a language keyboard.

    Triggered when the bot is added to a chat (``my_chat_member``) or by the
    /start command. Deliberately bilingual because no language has been
    chosen yet.

    Args:
        chat_id: Telegram chat to greet.
        client:  Client used to send the message.
    """
    client.send_message(
        chat_id=chat_id,
        text=bilingual_welcome(),
        reply_markup=_language_keyboard(),
    )


def handle_language_prompt(chat_id: int, client: TelegramClientProtocol) -> None:
    """Send just the language picker (the /language command).

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the message.
    """
    client.send_message(
        chat_id=chat_id,
        text=t(MessageKey.LANGUAGE_PROMPT, Language.EN),
        reply_markup=_language_keyboard(),
    )


def handle_language_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Persist the chosen language and confirm in that language.

    Acknowledges the button press, saves the choice, then edits the original
    message (which also removes the keyboard). Falls back to a fresh message
    if the original is no longer available.

    Args:
        query:          The CallbackQuery whose ``data`` is ``lang:<code>``.
        client:         Client used to acknowledge and confirm.
        settings_store: Store used to persist the chosen language.
    """
    data = query.data or ""
    try:
        lang = Language(data.removeprefix(LANGUAGE_CALLBACK_PREFIX))
    except ValueError:
        logger.warning("Unknown language callback", extra={"data": data})
        client.answer_callback_query(callback_query_id=query.id)
        return

    if query.message is None:
        logger.warning("Language callback without message", extra={"data": data})
        client.answer_callback_query(callback_query_id=query.id)
        return

    chat_id = query.message.chat.id
    settings_store.save(ChatSettings(chat_id=chat_id, language=lang, updated_at=utcnow()))
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.LANGUAGE_SET, lang),
    )


def handle_prices(
    chat_id: int,
    client: TelegramClientProtocol,
    octopus: OctopusClientProtocol,
    lang: Language,
    display_tz: ZoneInfo,
    tomorrow: bool = False,
) -> None:
    """Reply with an Agile price chart for today or tomorrow.

    "Today" and "tomorrow" are defined by local calendar days in
    ``display_tz``, converted to UTC for the Octopus API query.

    Args:
        chat_id:    Telegram chat to reply to.
        client:     Client used to send the reply.
        octopus:    Price client.
        lang:       Display language.
        display_tz: Timezone defining day boundaries and slot labels.
        tomorrow:   Fetch tomorrow's prices instead of today's.
    """
    target_day = utcnow().astimezone(display_tz).date() + timedelta(days=1 if tomorrow else 0)
    start_local = datetime.combine(target_day, time.min, tzinfo=display_tz)
    end_local = start_local + timedelta(days=1)

    try:
        points = octopus.get_prices(
            period_from=start_local.astimezone(UTC),
            period_to=end_local.astimezone(UTC),
        )
    except OctopusApiError:
        logger.exception("Octopus API error while handling /prices")
        client.send_message(chat_id=chat_id, text=t(MessageKey.SERVICE_UNAVAILABLE, lang))
        return

    if not points:
        key = MessageKey.PRICES_TOMORROW_UNAVAILABLE if tomorrow else MessageKey.PRICES_UNAVAILABLE
        client.send_message(chat_id=chat_id, text=t(key, lang))
        return

    header_key = MessageKey.PRICES_HEADER_TOMORROW if tomorrow else MessageKey.PRICES_HEADER_TODAY
    header = t(header_key, lang, date=target_day.isoformat())
    chart = render_price_chart(points=points, lang=lang, display_tz=display_tz)
    client.send_message(chat_id=chat_id, text=f"{header}\n{chart}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _language_keyboard() -> dict[str, object]:
    """Return the InlineKeyboardMarkup dict for the language picker."""
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="English", callback_data=f"{LANGUAGE_CALLBACK_PREFIX}{Language.EN}"
                ),
                InlineKeyboardButton(
                    text="中文", callback_data=f"{LANGUAGE_CALLBACK_PREFIX}{Language.ZH}"
                ),
            ]
        ]
    )
    return markup.model_dump()
