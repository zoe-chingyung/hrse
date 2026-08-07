"""Telegram command handlers.

Each function receives the minimum context it needs and sends exactly one
reply (callback handlers send an acknowledgement plus one edit). No business
logic beyond formatting the reply text.

Sprint 2A: /health
Sprint 2B: /laundry_done, /events, /summary
Sprint 6 : /start welcome flow, /language, /prices, language callback
Sprint C : button-driven onboarding (multi-select task picker + per-task
           button config), /profile, /reset, /tasks. Replaces the typed
           /setup conversation and retires /add_task, /remove_task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import TYPE_CHECKING
from zoneinfo import available_timezones

from aws_lambda_powertools import Logger
from pydantic import ValidationError

from hrse import __version__
from hrse.clients.octopus import REGION_LETTERS, OctopusApiError
from hrse.i18n import (
    MessageKey,
    bilingual_already_registered,
    bilingual_invite_required,
    bilingual_welcome,
    t,
)
from hrse.models.chat_settings import ChatSettings, Language, TaskProfile
from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.models.telegram import InlineKeyboardButton, InlineKeyboardMarkup
from hrse.services.price_chart import render_price_chart
from hrse.utils.datetime_utils import parse_hhmm, utcnow

if TYPE_CHECKING:
    from collections.abc import Callable
    from zoneinfo import ZoneInfo

    from hrse.clients.octopus import OctopusClientProtocol
    from hrse.models.telegram import TelegramCallbackQuery
    from hrse.store.chat_settings_store import ChatSettingsStore
    from hrse.store.protocol import EventStore
    from hrse.telegram.client import TelegramClientProtocol

logger = Logger(child=True)

LANGUAGE_CALLBACK_PREFIX = "lang:"
REGION_CALLBACK_PREFIX = "region:"
TASK_TOGGLE_CALLBACK_PREFIX = "task:"
TASK_DONE_CALLBACK_DATA = "task_done"
CONFIG_CALLBACK_PREFIX = "cfg:"
_CONFIG_OTHER_TOKEN = "other"

# Canonical onboarding order — also drives multi-select button layout and
# the per-task config queue order.
TASK_ORDER: tuple[str, ...] = ("laundry", "dishwasher", "ev")

_POSTCODE_STEP = 0


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
# Sprint A — invite-only registration gate
# ---------------------------------------------------------------------------


def handle_start(
    chat_id: int,
    args: list[str],
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    invite_code: str,
) -> None:
    """Gate self-service registration behind a shared invite code.

    A stranger running /start with no or the wrong code must never become a
    recipient, so no ``ChatSettings`` is created in that case. A chat that
    has already completed onboarding is told to use /reset instead of being
    silently re-registered, which would wipe its saved profile.

    Args:
        chat_id:        Telegram chat requesting registration.
        args:           Command arguments; ``args[0]`` is the invite code.
        client:         Client used to send the reply.
        settings_store: Store used to check for / create this chat's settings.
        invite_code:    The configured shared invite code to match against.
    """
    existing = settings_store.get(chat_id)
    if existing is not None and existing.onboarding_complete:
        client.send_message(chat_id=chat_id, text=bilingual_already_registered())
        return

    supplied_code = args[0] if args else None
    if not invite_code or supplied_code != invite_code:
        client.send_message(chat_id=chat_id, text=bilingual_invite_required())
        return

    settings_store.save(
        ChatSettings(chat_id=chat_id, onboarding_complete=False, updated_at=utcnow())
    )
    handle_welcome(chat_id=chat_id, client=client)


# ---------------------------------------------------------------------------
# Sprint 6 — welcome, language
# ---------------------------------------------------------------------------


def handle_welcome(chat_id: int, client: TelegramClientProtocol) -> None:
    """Send the bilingual onboarding message with a language keyboard.

    Triggered when the bot is added to a chat (``my_chat_member``), by the
    /start command, or by /reset restarting the button flow from the top.
    Deliberately bilingual because no language has been chosen yet.

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
    message (which also removes the keyboard). A chat that hasn't finished
    onboarding continues straight into the postcode step; a chat changing
    its language via /language (already onboarded) just gets the confirmation.

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
    existing = settings_store.get(chat_id)
    updated = (
        existing.model_copy(update={"language": lang, "updated_at": utcnow()})
        if existing is not None
        else ChatSettings(chat_id=chat_id, language=lang, updated_at=utcnow())
    )
    settings_store.save(updated)
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.LANGUAGE_SET, lang),
    )
    if not updated.onboarding_complete:
        _start_postcode_step(chat_id, client, settings_store, updated)


def handle_region_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Persist a manually-picked GSP region letter and continue onboarding.

    Fallback path for when postcode lookup fails (or no Octopus client was
    available) — mirrors ``handle_language_callback``'s button pattern.
    Only acts while the chat is actually waiting at the postcode step; a
    stale button press (already resolved, or onboarding restarted since) is
    just acknowledged.

    Args:
        query:          The CallbackQuery whose ``data`` is ``region:<letter>``.
        client:         Client used to acknowledge and confirm.
        settings_store: Store used to load/persist the chat's settings.
    """
    data = query.data or ""
    letter = data.removeprefix(REGION_CALLBACK_PREFIX)
    if letter not in REGION_LETTERS:
        logger.warning("Unknown region callback", extra={"data": data})
        client.answer_callback_query(callback_query_id=query.id)
        return

    if query.message is None:
        logger.warning("Region callback without message", extra={"data": data})
        client.answer_callback_query(callback_query_id=query.id)
        return

    chat_id = query.message.chat.id
    settings = settings_store.get(chat_id)
    if settings is None or settings.onboarding_stage != "postcode":
        client.answer_callback_query(callback_query_id=query.id)
        return

    lang = settings.language
    updated = settings.model_copy(update={"octopus_region_code": letter, "updated_at": utcnow()})
    settings_store.save(updated)
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.SETUP_REGION_CONFIRMED, lang, region=letter),
    )
    _start_task_selection(chat_id, client, settings_store, updated)


def handle_prices(
    chat_id: int,
    client: TelegramClientProtocol,
    octopus: OctopusClientProtocol,
    lang: Language,
    display_tz: ZoneInfo,
    window_slots: int = 4,
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
        display_tz:   Timezone defining day boundaries and slot labels.
        window_slots: Length of the cheapest window to highlight, in slots.
        tomorrow:     Fetch tomorrow's prices instead of today's.
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
    chart = render_price_chart(
        points=points, lang=lang, display_tz=display_tz, window_slots=window_slots
    )
    client.send_message(chat_id=chat_id, text=f"{header}\n{chart}")


# ---------------------------------------------------------------------------
# Sprint C — button-driven onboarding
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ButtonQuestion:
    """One button-driven question in a task's per-task config flow."""

    field: str
    message_key: MessageKey
    options: tuple[tuple[str, str], ...]  # (button label, value string)
    parser: Callable[[str], object]
    allow_other: bool = True


def _parse_int(text: str) -> int:
    """Parse a plain integer answer; range constraints are enforced by TaskProfile."""
    return int(text.strip())


def _parse_float(text: str) -> float:
    """Parse a plain float answer; range constraints are enforced by TaskProfile."""
    return float(text.strip())


def _parse_setup_hhmm(text: str) -> str:
    """Parse an HH:MM answer, normalising to zero-padded 24h form."""
    return parse_hhmm(text.strip()).strftime("%H:%M")


def _parse_setup_bool(text: str) -> bool:
    """Parse a yes/no answer."""
    normalized = text.strip().lower()
    if normalized in {"yes", "y", "true", "1"}:
        return True
    if normalized in {"no", "n", "false", "0"}:
        return False
    raise ValueError(f"expected yes/no, got {text!r}")


def _parse_setup_timezone(text: str) -> str:
    """Parse an IANA timezone name answer."""
    value = text.strip()
    if value not in available_timezones():
        raise ValueError(f"unknown IANA timezone, got {value!r}")
    return value


# Display label per TASK_REGISTRY key. Distinct from NotificationService's
# task-name labels (keyed by Recommendation.task, e.g. "ev_charging") since
# these commands operate on registry keys (e.g. "ev") instead.
_TASK_DISPLAY: dict[str, str] = {
    "laundry": "🧺 Laundry",
    "dishwasher": "🍽 Dishwasher",
    "ev": "🔌 EV Charging",
}


def _task_display(task_name: str) -> str:
    """Return a display label for a TASK_REGISTRY key."""
    return _TASK_DISPLAY.get(task_name, task_name)


_TIME_OPTIONS_EARLY = (
    ("06:00", "06:00"),
    ("07:00", "07:00"),
    ("08:00", "08:00"),
    ("09:00", "09:00"),
)
_TIME_OPTIONS_LATE = (
    ("20:00", "20:00"),
    ("21:00", "21:00"),
    ("22:00", "22:00"),
    ("23:00", "23:00"),
)
_TIMEZONE_OPTIONS = (("Europe/London", "Europe/London"), ("Asia/Hong_Kong", "Asia/Hong_Kong"))

_LAUNDRY_QUESTIONS: tuple[_ButtonQuestion, ...] = (
    _ButtonQuestion(
        "target_per_week",
        MessageKey.SETUP_Q_TARGET_RUNS,
        (("1", "1"), ("2", "2"), ("3", "3"), ("4", "4")),
        _parse_int,
    ),
    _ButtonQuestion(
        "duration_slots",
        MessageKey.SETUP_Q_DURATION,
        (("1h", "2"), ("1.5h", "3"), ("2h", "4"), ("3h", "6")),
        _parse_int,
    ),
    _ButtonQuestion(
        "wash_budget_pence",
        MessageKey.SETUP_Q_BUDGET,
        (("20p", "20"), ("40p", "40"), ("60p", "60"), ("80p", "80")),
        _parse_float,
    ),
    _ButtonQuestion(
        "earliest_start", MessageKey.SETUP_Q_EARLIEST, _TIME_OPTIONS_EARLY, _parse_setup_hhmm
    ),
    _ButtonQuestion(
        "latest_finish", MessageKey.SETUP_Q_LATEST, _TIME_OPTIONS_LATE, _parse_setup_hhmm
    ),
    _ButtonQuestion(
        "outdoor_drying",
        MessageKey.SETUP_Q_OUTDOOR_DRYING,
        (("Yes", "yes"), ("No", "no")),
        _parse_setup_bool,
        allow_other=False,
    ),
    _ButtonQuestion(
        "min_uv",
        MessageKey.SETUP_Q_MIN_UV,
        (("0", "0"), ("1", "1"), ("3", "3"), ("5", "5")),
        _parse_float,
    ),
    _ButtonQuestion(
        "max_rain_probability",
        MessageKey.SETUP_Q_MAX_RAIN,
        (("20%", "20"), ("40%", "40"), ("60%", "60"), ("80%", "80")),
        _parse_int,
    ),
    _ButtonQuestion(
        "timezone", MessageKey.SETUP_Q_TIMEZONE, _TIMEZONE_OPTIONS, _parse_setup_timezone
    ),
)

_DISHWASHER_QUESTIONS: tuple[_ButtonQuestion, ...] = (
    _ButtonQuestion(
        "target_per_week",
        MessageKey.SETUP_Q_TARGET_RUNS,
        (("3", "3"), ("5", "5"), ("7", "7"), ("10", "10")),
        _parse_int,
    ),
    _ButtonQuestion(
        "duration_slots",
        MessageKey.SETUP_Q_DURATION,
        (("1h", "2"), ("1.5h", "3"), ("2h", "4")),
        _parse_int,
    ),
    _ButtonQuestion(
        "wash_budget_pence",
        MessageKey.SETUP_Q_BUDGET,
        (("15p", "15"), ("25p", "25"), ("35p", "35"), ("50p", "50")),
        _parse_float,
    ),
    _ButtonQuestion(
        "earliest_start", MessageKey.SETUP_Q_EARLIEST, _TIME_OPTIONS_EARLY, _parse_setup_hhmm
    ),
    _ButtonQuestion(
        "latest_finish", MessageKey.SETUP_Q_LATEST, _TIME_OPTIONS_LATE, _parse_setup_hhmm
    ),
    _ButtonQuestion(
        "timezone", MessageKey.SETUP_Q_TIMEZONE, _TIMEZONE_OPTIONS, _parse_setup_timezone
    ),
)

# EV's single required input (per product decision: no deadline, no kWh yet).
# The "ev" registry key differs from EVChargingConfig.task_name
# ("ev_charging") — see build_task_config's docstring for the guard this
# mirrors; here it only matters for _TASK_DISPLAY / _TASK_QUESTIONS lookups,
# which are always keyed by the registry key "ev".
_EV_QUESTIONS: tuple[_ButtonQuestion, ...] = (
    _ButtonQuestion(
        "duration_slots",
        MessageKey.SETUP_Q_EV_DURATION,
        (("4h", "8"), ("6h", "12"), ("8h", "16"), ("10h", "20")),
        _parse_int,
        allow_other=False,
    ),
)

_TASK_QUESTIONS: dict[str, tuple[_ButtonQuestion, ...]] = {
    "laundry": _LAUNDRY_QUESTIONS,
    "dishwasher": _DISHWASHER_QUESTIONS,
    "ev": _EV_QUESTIONS,
}


def _default_profile_for_task(task_key: str) -> TaskProfile:
    """Return the starting ``TaskProfile`` created when a task is selected.

    Per-task button questions (see ``_TASK_QUESTIONS``) then overwrite
    individual fields as the user answers. ``weather_aware`` is set once
    here rather than asked, since it's a fixed property of the task type,
    not a user preference.
    """
    if task_key == "laundry":
        return TaskProfile()
    if task_key == "dishwasher":
        return TaskProfile(weather_aware=False)
    if task_key == "ev":
        # "No deadline" (product decision) — search the whole day, not just
        # overnight, for the cheapest contiguous charge window.
        return TaskProfile(weather_aware=False, earliest_start="00:00", latest_finish="23:30")
    raise KeyError(task_key)


def _start_postcode_step(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
) -> None:
    """Advance to (or restart) the postcode/region question."""
    updated = settings.model_copy(
        update={
            "onboarding_stage": "postcode",
            "onboarding_step": _POSTCODE_STEP,
            "updated_at": utcnow(),
        }
    )
    settings_store.save(updated)
    client.send_message(chat_id=chat_id, text=t(MessageKey.SETUP_Q_POSTCODE, updated.language))


def _start_task_selection(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
) -> None:
    """Advance to the multi-select task picker with an empty selection."""
    updated = settings.model_copy(
        update={
            "onboarding_stage": "tasks",
            "onboarding_step": None,
            "pending_task_selection": [],
            "updated_at": utcnow(),
        }
    )
    settings_store.save(updated)
    client.send_message(
        chat_id=chat_id,
        text=t(MessageKey.SETUP_Q_TASK_SELECT, updated.language),
        reply_markup=_task_select_keyboard([], updated.language),
    )


def _done_label(lang: Language) -> str:
    return "✅ Done" if lang is Language.EN else "✅ 完成"


def _other_label(lang: Language) -> str:
    return "Other" if lang is Language.EN else "其他"


def _task_select_keyboard(selected: list[str], lang: Language) -> dict[str, object]:
    """Build the multi-select task picker keyboard, checkmarking ``selected``."""
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'✅' if key in selected else '⬜'} {_task_display(key)}",
                callback_data=f"{TASK_TOGGLE_CALLBACK_PREFIX}{key}",
            )
        ]
        for key in TASK_ORDER
    ]
    rows.append(
        [InlineKeyboardButton(text=_done_label(lang), callback_data=TASK_DONE_CALLBACK_DATA)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows).model_dump()


def _config_keyboard(question: _ButtonQuestion, lang: Language) -> dict[str, object]:
    """Build the button keyboard for one per-task config question."""
    buttons = [
        InlineKeyboardButton(
            text=label, callback_data=f"{CONFIG_CALLBACK_PREFIX}{question.field}:{value}"
        )
        for label, value in question.options
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    if question.allow_other:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_other_label(lang),
                    callback_data=f"{CONFIG_CALLBACK_PREFIX}{question.field}:{_CONFIG_OTHER_TOKEN}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows).model_dump()


def handle_task_toggle_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Toggle one task on/off in the multi-select picker and redraw it."""
    data = query.data or ""
    task_key = data.removeprefix(TASK_TOGGLE_CALLBACK_PREFIX)

    if query.message is None or task_key not in TASK_ORDER:
        client.answer_callback_query(callback_query_id=query.id)
        return

    chat_id = query.message.chat.id
    settings = settings_store.get(chat_id)
    if settings is None or settings.onboarding_stage != "tasks":
        client.answer_callback_query(callback_query_id=query.id)
        return

    selection = list(settings.pending_task_selection)
    if task_key in selection:
        selection.remove(task_key)
    else:
        selection.append(task_key)

    updated = settings.model_copy(
        update={"pending_task_selection": selection, "updated_at": utcnow()}
    )
    settings_store.save(updated)
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.SETUP_Q_TASK_SELECT, settings.language),
        reply_markup=_task_select_keyboard(selection, settings.language),
    )


def handle_task_done_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Lock in the multi-select and move to per-task button config.

    Blocks (re-shows the picker) if zero tasks are selected. Creates a
    default ``TaskProfile`` per selected task, in canonical ``TASK_ORDER``,
    and starts asking the first task's questions.
    """
    if query.message is None:
        client.answer_callback_query(callback_query_id=query.id)
        return

    chat_id = query.message.chat.id
    settings = settings_store.get(chat_id)
    if settings is None or settings.onboarding_stage != "tasks":
        client.answer_callback_query(callback_query_id=query.id)
        return

    lang = settings.language
    client.answer_callback_query(callback_query_id=query.id)

    if not settings.pending_task_selection:
        client.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text=t(MessageKey.SETUP_TASKS_NONE_SELECTED, lang)
            + "\n\n"
            + t(MessageKey.SETUP_Q_TASK_SELECT, lang),
            reply_markup=_task_select_keyboard(settings.pending_task_selection, lang),
        )
        return

    selected = [key for key in TASK_ORDER if key in settings.pending_task_selection]
    profiles = {**settings.profiles, **{key: _default_profile_for_task(key) for key in selected}}
    updated = settings.model_copy(
        update={
            "profiles": profiles,
            "enabled_tasks": selected,
            "onboarding_stage": "config",
            "pending_task_selection": [],
            "pending_config_queue": selected,
            "onboarding_task_step": 0,
            "updated_at": utcnow(),
        }
    )
    settings_store.save(updated)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(
            MessageKey.SETUP_TASKS_LOCKED,
            lang,
            tasks=", ".join(_task_display(key) for key in selected),
        ),
    )
    _send_config_question(chat_id, client, updated)


def _send_config_question(
    chat_id: int, client: TelegramClientProtocol, settings: ChatSettings
) -> None:
    """Send the current per-task button question for ``settings``."""
    task_key = settings.pending_config_queue[0]
    questions = _TASK_QUESTIONS[task_key]
    step = settings.onboarding_task_step
    question = questions[step]
    client.send_message(
        chat_id=chat_id,
        text=t(
            question.message_key,
            settings.language,
            step=step + 1,
            total=len(questions),
            task=_task_display(task_key),
        ),
        reply_markup=_config_keyboard(question, settings.language),
    )


def handle_config_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Handle a button press answering one per-task config question."""
    data = query.data or ""
    payload = data.removeprefix(CONFIG_CALLBACK_PREFIX)
    field, _, value_token = payload.partition(":")

    if query.message is None:
        client.answer_callback_query(callback_query_id=query.id)
        return

    chat_id = query.message.chat.id
    settings = settings_store.get(chat_id)
    if (
        settings is None
        or settings.onboarding_stage != "config"
        or not settings.pending_config_queue
    ):
        client.answer_callback_query(callback_query_id=query.id)
        return

    task_key = settings.pending_config_queue[0]
    questions = _TASK_QUESTIONS[task_key]
    step = settings.onboarding_task_step
    if step >= len(questions) or questions[step].field != field:
        # Stale button from a previous question/task — ignore.
        client.answer_callback_query(callback_query_id=query.id)
        return

    question = questions[step]
    lang = settings.language
    client.answer_callback_query(callback_query_id=query.id)

    if value_token == _CONFIG_OTHER_TOKEN:
        updated = settings.model_copy(
            update={"awaiting_typed_field": field, "updated_at": utcnow()}
        )
        settings_store.save(updated)
        client.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text=t(
                question.message_key,
                lang,
                step=step + 1,
                total=len(questions),
                task=_task_display(task_key),
            )
            + "\n\n"
            + t(MessageKey.SETUP_TYPE_YOUR_ANSWER, lang),
        )
        return

    label = next((lbl for lbl, val in question.options if val == value_token), value_token)
    try:
        value = question.parser(value_token)
        profile = settings.profiles.get(task_key) or TaskProfile()
        updated_profile = TaskProfile(**{**profile.model_dump(), field: value})
    except (ValueError, ValidationError):
        client.edit_message_text(
            chat_id=chat_id,
            message_id=query.message.message_id,
            text=t(MessageKey.SETUP_INVALID_ANSWER, lang)
            + "\n\n"
            + t(
                question.message_key,
                lang,
                step=step + 1,
                total=len(questions),
                task=_task_display(task_key),
            ),
            reply_markup=_config_keyboard(question, lang),
        )
        return

    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.SETUP_OPTION_CONFIRMED, lang, label=label),
    )
    _advance_config(chat_id, client, settings_store, settings, task_key, updated_profile)


def handle_onboarding_answer(
    chat_id: int,
    text: str,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
    octopus: OctopusClientProtocol | None = None,
) -> None:
    """Process a plain-text reply during an active onboarding conversation.

    Only two situations expect free text: the postcode question, and an
    "Other" button's typed follow-up during per-task config. Anything else
    (including plain text during the multi-select picker) gets a reminder
    to use the buttons.

    Args:
        chat_id:        Telegram chat mid-onboarding.
        text:           The raw message text (the answer).
        client:         Client used to send the next question or confirmation.
        settings_store: Store used to load/persist onboarding progress.
        lang:           Display language.
        octopus:        Used for the postcode→region lookup. If unavailable,
                         lookup is skipped and the manual region-picker
                         fallback is shown directly.
    """
    settings = settings_store.get(chat_id)
    if settings is None or settings.onboarding_stage is None:
        # Router only routes here when onboarding is active; defensive fallback.
        handle_unknown(chat_id=chat_id, text=text, client=client, lang=lang)
        return

    if settings.onboarding_stage == "postcode":
        _handle_postcode_answer(chat_id, text, client, settings_store, settings, octopus)
        return

    if settings.onboarding_stage == "config" and settings.awaiting_typed_field is not None:
        _handle_typed_config_answer(chat_id, text, client, settings_store, settings)
        return

    client.send_message(
        chat_id=chat_id, text=t(MessageKey.SETUP_USE_BUTTONS_HINT, settings.language)
    )


def _handle_postcode_answer(
    chat_id: int,
    text: str,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
    octopus: OctopusClientProtocol | None,
) -> None:
    """Resolve a postcode answer to a GSP region, or fall back to manual pick.

    On success, advances onboarding to the multi-select task picker and
    confirms the resolved region. On failure — no Octopus client available,
    or the lookup itself finds no/an ambiguous match — the region-picker
    keyboard is shown and the user can either tap a region or resend a
    postcode.
    """
    lang = settings.language
    region = octopus.lookup_gsp(text.strip()) if octopus is not None else None

    if region is None:
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.SETUP_REGION_LOOKUP_FAILED, lang),
            reply_markup=_region_keyboard(),
        )
        return

    updated = settings.model_copy(update={"octopus_region_code": region, "updated_at": utcnow()})
    settings_store.save(updated)
    client.send_message(
        chat_id=chat_id, text=t(MessageKey.SETUP_REGION_CONFIRMED, lang, region=region)
    )
    _start_task_selection(chat_id, client, settings_store, updated)


def _handle_typed_config_answer(
    chat_id: int,
    text: str,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
) -> None:
    """Process a typed "Other" answer during per-task button config."""
    lang = settings.language
    task_key = settings.pending_config_queue[0]
    questions = _TASK_QUESTIONS[task_key]
    step = settings.onboarding_task_step
    question = questions[step]

    try:
        value = question.parser(text)
        profile = settings.profiles.get(task_key) or TaskProfile()
        updated_profile = TaskProfile(**{**profile.model_dump(), question.field: value})
    except (ValueError, ValidationError):
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.SETUP_INVALID_ANSWER, lang)
            + "\n\n"
            + t(
                question.message_key,
                lang,
                step=step + 1,
                total=len(questions),
                task=_task_display(task_key),
            ),
        )
        return

    _advance_config(chat_id, client, settings_store, settings, task_key, updated_profile)


def _advance_config(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
    task_key: str,
    updated_profile: TaskProfile,
) -> None:
    """Save the just-answered field and move to the next question/task/finish."""
    profiles = {**settings.profiles, task_key: updated_profile}
    questions = _TASK_QUESTIONS[task_key]
    next_step = settings.onboarding_task_step + 1

    if next_step < len(questions):
        updated = settings.model_copy(
            update={
                "profiles": profiles,
                "onboarding_task_step": next_step,
                "awaiting_typed_field": None,
                "updated_at": utcnow(),
            }
        )
        settings_store.save(updated)
        _send_config_question(chat_id, client, updated)
        return

    remaining_queue = settings.pending_config_queue[1:]
    if remaining_queue:
        updated = settings.model_copy(
            update={
                "profiles": profiles,
                "pending_config_queue": remaining_queue,
                "onboarding_task_step": 0,
                "awaiting_typed_field": None,
                "updated_at": utcnow(),
            }
        )
        settings_store.save(updated)
        _send_config_question(chat_id, client, updated)
        return

    updated = settings.model_copy(
        update={
            "profiles": profiles,
            "pending_config_queue": [],
            "onboarding_task_step": 0,
            "awaiting_typed_field": None,
            "onboarding_stage": None,
            "onboarding_complete": True,
            "updated_at": utcnow(),
        }
    )
    settings_store.save(updated)
    client.send_message(
        chat_id=chat_id,
        text=t(
            MessageKey.SETUP_COMPLETE_SUMMARY,
            updated.language,
            tasks=", ".join(_task_display(key) for key in updated.enabled_tasks),
        ),
    )


def handle_profile(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Reply with this chat's current settings, one block per configured task.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the reply.
        settings_store: Store used to load the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    profiles = settings.profiles if settings is not None else {}

    if not profiles:
        client.send_message(chat_id=chat_id, text=t(MessageKey.PROFILE_NONE, lang))
        return

    blocks = "".join(
        t(
            MessageKey.PROFILE_TASK_BLOCK,
            lang,
            task=_task_display(task_key),
            target=profile.target_per_week,
            duration=f"{profile.duration_slots * 0.5:g}h",
            earliest=profile.earliest_start,
            latest=profile.latest_finish,
            budget=f"{profile.wash_budget_pence:g}",
            weather="✅" if profile.weather_aware else "❌",
        )
        for task_key in TASK_ORDER
        if (profile := profiles.get(task_key)) is not None
    )
    client.send_message(chat_id=chat_id, text=t(MessageKey.PROFILE_HEADER, lang, blocks=blocks))


def handle_reset(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Wipe this chat's task setup and restart the button onboarding flow.

    Drops the chat from daily-notification recipients (``onboarding_complete``
    becomes False) until it completes setup again. Idempotent and safe to
    call mid-onboarding — it always resets to a clean slate.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the confirmation.
        settings_store: Store used to load and persist the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    updated = ChatSettings(
        chat_id=chat_id,
        language=settings.language if settings is not None else lang,
        octopus_region_code=settings.octopus_region_code if settings is not None else None,
        enabled_tasks=[],
        updated_at=utcnow(),
    )
    settings_store.save(updated)
    client.send_message(chat_id=chat_id, text=t(MessageKey.RESET_DONE, updated.language))
    handle_welcome(chat_id=chat_id, client=client)


# ---------------------------------------------------------------------------
# /tasks — read-only view of the currently enabled tasks
# ---------------------------------------------------------------------------


def handle_tasks(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Reply with this chat's currently enabled tasks (read-only).

    Task selection is set once during onboarding via the button picker;
    changing it means running /reset and redoing setup.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the reply.
        settings_store: Store used to load the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    enabled = settings.enabled_tasks if settings is not None else []
    if not enabled:
        client.send_message(chat_id=chat_id, text=t(MessageKey.PROFILE_NONE, lang))
        return
    lines = "\n".join(f"  • {_task_display(name)}" for name in enabled)
    client.send_message(chat_id=chat_id, text=t(MessageKey.TASKS_LIST, lang, tasks=lines))


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


# GSP region letter -> display name, per Octopus's published region list.
_REGION_DISPLAY: dict[str, str] = {
    "A": "Eastern",
    "B": "East Midlands",
    "C": "London",
    "D": "Merseyside",
    "E": "Midlands",
    "F": "North East",
    "G": "North West",
    "H": "Southern",
    "J": "South East",
    "K": "South West",
    "L": "Yorkshire",
    "M": "South Scotland",
    "N": "North Scotland",
    "P": "North Wales",
}


def _region_keyboard() -> dict[str, object]:
    """Return the InlineKeyboardMarkup dict for manual GSP region selection.

    Two buttons per row, in ``REGION_LETTERS`` order — the manual fallback
    shown when postcode lookup fails or no Octopus client is available.
    """
    buttons = [
        InlineKeyboardButton(
            text=f"{letter} — {_REGION_DISPLAY[letter]}",
            callback_data=f"{REGION_CALLBACK_PREFIX}{letter}",
        )
        for letter in REGION_LETTERS
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows).model_dump()
