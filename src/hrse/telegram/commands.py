"""Telegram command handlers.

Each function receives the minimum context it needs and sends exactly one
reply (the language callback sends an acknowledgement plus one edit). No
business logic beyond formatting the reply text.

Sprint 2A: /health
Sprint 2B: /laundry_done, /events, /summary
Sprint 6 : /start welcome flow, /language, /prices, language callback
Sprint 5B: /setup onboarding conversation, /profile, /reset
Sprint 5C: /tasks, /add_task, /remove_task
"""

from __future__ import annotations

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
from hrse.models.task_config import TASK_REGISTRY
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
    existing = settings_store.get(chat_id)
    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=lang,
            profiles=existing.profiles if existing is not None else {},
            onboarding_step=existing.onboarding_step if existing is not None else None,
            enabled_tasks=existing.enabled_tasks if existing is not None else ["laundry"],
            onboarding_complete=existing.onboarding_complete if existing is not None else False,
            octopus_region_code=existing.octopus_region_code if existing is not None else None,
            updated_at=utcnow(),
        )
    )
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.LANGUAGE_SET, lang),
    )


def handle_region_callback(
    query: TelegramCallbackQuery,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
) -> None:
    """Persist a manually-picked GSP region letter and resume /setup.

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
    if settings is None or settings.onboarding_step != _POSTCODE_STEP:
        client.answer_callback_query(callback_query_id=query.id)
        return

    lang = settings.language
    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=lang,
            profiles=settings.profiles,
            onboarding_step=_POSTCODE_STEP + 1,
            enabled_tasks=settings.enabled_tasks,
            onboarding_complete=settings.onboarding_complete,
            octopus_region_code=letter,
            updated_at=utcnow(),
        )
    )
    client.answer_callback_query(callback_query_id=query.id)
    client.edit_message_text(
        chat_id=chat_id,
        message_id=query.message.message_id,
        text=t(MessageKey.SETUP_REGION_CONFIRMED, lang, region=letter),
    )
    _send_setup_question(chat_id, client, lang, step=_POSTCODE_STEP + 1)


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
# Sprint 5B — /setup onboarding conversation, /profile, /reset
# ---------------------------------------------------------------------------


def _parse_setup_target(text: str) -> int:
    """Parse the runs-per-week answer; must be a positive integer."""
    value = int(text.strip())
    if value < 1:
        raise ValueError("target_per_week must be >= 1")
    return value


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


def _parse_setup_budget(text: str) -> float:
    """Parse a wash-budget-in-pence answer; must be positive."""
    value = float(text.strip())
    if value <= 0:
        raise ValueError("wash_budget_pence must be > 0")
    return value


# Each step: (TaskProfile field name, question MessageKey, answer parser).
# duration_slots, machine_kwh, min_uv, and max_rain_probability are
# deliberately not asked — they keep TaskProfile's defaults, per spec, to
# keep the onboarding flow short.
# NOTE (5D.1): still laundry-only — /setup always configures profiles["laundry"].
# Per-task step lists and `/setup <task>` land in 5D.2.
_SETUP_STEPS: tuple[tuple[str, MessageKey, Callable[[str], object]], ...] = (
    ("target_per_week", MessageKey.SETUP_Q_LAUNDRY_TARGET, _parse_setup_target),
    ("earliest_start", MessageKey.SETUP_Q_EARLIEST_START, _parse_setup_hhmm),
    ("latest_finish", MessageKey.SETUP_Q_LATEST_FINISH, _parse_setup_hhmm),
    ("outdoor_drying", MessageKey.SETUP_Q_OUTDOOR_DRYING, _parse_setup_bool),
    ("timezone", MessageKey.SETUP_Q_TIMEZONE, _parse_setup_timezone),
    ("wash_budget_pence", MessageKey.SETUP_Q_WASH_BUDGET, _parse_setup_budget),
)

_SETUP_TASK_KEY = "laundry"

# Step 0 asks for postcode/region (Sprint B) — a ChatSettings-level field,
# not a TaskProfile one — so it's handled separately from _SETUP_STEPS
# below and doesn't appear in that table. Steps 1..len(_SETUP_STEPS) map to
# _SETUP_STEPS[step - 1]. Total question count includes the postcode step.
_POSTCODE_STEP = 0
_TOTAL_SETUP_QUESTIONS = len(_SETUP_STEPS) + 1


def handle_setup_start(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Start (or restart) the /setup onboarding conversation.

    Resets this chat's laundry profile to fresh defaults and asks question 0
    (postcode/region); "restart" means starting over, not resuming a
    half-finished attempt. Other tasks' profiles, this chat's enabled tasks,
    and its previously-resolved region are preserved until overwritten by a
    fresh answer.

    Args:
        chat_id:        Telegram chat to onboard.
        client:         Client used to send the question.
        settings_store: Store used to persist onboarding progress.
        lang:           Display language for the questions.
    """
    existing = settings_store.get(chat_id)
    profiles = dict(existing.profiles) if existing is not None else {}
    profiles[_SETUP_TASK_KEY] = TaskProfile()
    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=lang,
            profiles=profiles,
            onboarding_step=_POSTCODE_STEP,
            enabled_tasks=existing.enabled_tasks if existing is not None else ["laundry"],
            onboarding_complete=existing.onboarding_complete if existing is not None else False,
            octopus_region_code=existing.octopus_region_code if existing is not None else None,
            updated_at=utcnow(),
        )
    )
    _send_setup_question(chat_id, client, lang, step=_POSTCODE_STEP)


def handle_onboarding_answer(
    chat_id: int,
    text: str,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
    octopus: OctopusClientProtocol | None = None,
) -> None:
    """Process a plain-text reply during an active /setup conversation.

    Step 0 (postcode/region) is handled separately since it's a
    ChatSettings-level field resolved via a network lookup, not a
    TaskProfile field. For the remaining steps: validates the answer
    against the current step; on failure, re-asks the same question with a
    hint rather than advancing. On the final step, finalises the profile
    and clears ``onboarding_step``.

    Args:
        chat_id:        Telegram chat mid-onboarding.
        text:           The raw message text (the answer).
        client:         Client used to send the next question or confirmation.
        settings_store: Store used to load/persist onboarding progress.
        lang:           Display language.
        octopus:        Used for the postcode→region lookup at step 0. If
                         unavailable, lookup is skipped and the manual
                         region-picker fallback is shown directly.
    """
    settings = settings_store.get(chat_id)
    if settings is None or settings.onboarding_step is None:
        # Router only routes here when onboarding is active; defensive fallback.
        handle_unknown(chat_id=chat_id, text=text, client=client, lang=lang)
        return

    step = settings.onboarding_step

    if step == _POSTCODE_STEP:
        _handle_postcode_answer(chat_id, text, client, settings_store, settings, lang, octopus)
        return

    field_name, question_key, parser = _SETUP_STEPS[step - 1]
    profile = settings.profiles.get(_SETUP_TASK_KEY) or TaskProfile()

    try:
        value = parser(text)
        updated_profile = TaskProfile(**{**profile.model_dump(), field_name: value})
    except (ValueError, ValidationError):
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.SETUP_INVALID_ANSWER, lang)
            + "\n\n"
            + t(question_key, lang, step=step + 1, total=_TOTAL_SETUP_QUESTIONS),
        )
        return

    next_step = step + 1
    is_done = next_step >= _TOTAL_SETUP_QUESTIONS
    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=settings.language,
            profiles={**settings.profiles, _SETUP_TASK_KEY: updated_profile},
            onboarding_step=None if is_done else next_step,
            enabled_tasks=settings.enabled_tasks,
            onboarding_complete=True if is_done else settings.onboarding_complete,
            octopus_region_code=settings.octopus_region_code,
            updated_at=utcnow(),
        )
    )

    if is_done:
        client.send_message(chat_id=chat_id, text=t(MessageKey.SETUP_DONE, lang))
    else:
        _send_setup_question(chat_id, client, lang, step=next_step)


def _handle_postcode_answer(
    chat_id: int,
    text: str,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    settings: ChatSettings,
    lang: Language,
    octopus: OctopusClientProtocol | None,
) -> None:
    """Resolve a postcode answer to a GSP region, or fall back to manual pick.

    On success, advances onboarding to step 1 (the first TaskProfile
    question) and confirms the resolved region. On failure — no Octopus
    client available, or the lookup itself finds no/an ambiguous match —
    ``onboarding_step`` does not advance; the region-picker keyboard is
    shown and the user can either tap a region or resend a postcode.
    """
    region = octopus.lookup_gsp(text.strip()) if octopus is not None else None

    if region is None:
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.SETUP_REGION_LOOKUP_FAILED, lang),
            reply_markup=_region_keyboard(),
        )
        return

    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=settings.language,
            profiles=settings.profiles,
            onboarding_step=_POSTCODE_STEP + 1,
            enabled_tasks=settings.enabled_tasks,
            onboarding_complete=settings.onboarding_complete,
            octopus_region_code=region,
            updated_at=utcnow(),
        )
    )
    client.send_message(
        chat_id=chat_id, text=t(MessageKey.SETUP_REGION_CONFIRMED, lang, region=region)
    )
    _send_setup_question(chat_id, client, lang, step=_POSTCODE_STEP + 1)


def handle_profile(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Reply with this chat's current laundry settings.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the reply.
        settings_store: Store used to load the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    profile = settings.profiles.get(_SETUP_TASK_KEY) if settings is not None else None

    if profile is None:
        client.send_message(chat_id=chat_id, text=t(MessageKey.PROFILE_NONE, lang))
        return

    client.send_message(
        chat_id=chat_id,
        text=t(
            MessageKey.PROFILE_HEADER,
            lang,
            target=profile.target_per_week,
            earliest=profile.earliest_start,
            latest=profile.latest_finish,
            budget=f"{profile.wash_budget_pence:g}",
            outdoor="✅" if profile.outdoor_drying else "❌",
            timezone=profile.timezone or "—",
        ),
    )


def handle_reset(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Clear this chat's laundry profile, reverting it to the global defaults.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the confirmation.
        settings_store: Store used to load and persist the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    settings_store.save(
        ChatSettings(
            chat_id=chat_id,
            language=settings.language if settings is not None else lang,
            profiles={},
            onboarding_step=None,
            enabled_tasks=settings.enabled_tasks if settings is not None else ["laundry"],
            onboarding_complete=False,
            octopus_region_code=settings.octopus_region_code if settings is not None else None,
            updated_at=utcnow(),
        )
    )
    client.send_message(chat_id=chat_id, text=t(MessageKey.RESET_DONE, lang))


def _send_setup_question(
    chat_id: int, client: TelegramClientProtocol, lang: Language, step: int
) -> None:
    """Send the numbered question for ``step`` of the /setup conversation.

    ``step`` 0 is the postcode/region question; steps 1..len(_SETUP_STEPS)
    map to ``_SETUP_STEPS[step - 1]``.
    """
    if step == _POSTCODE_STEP:
        question_key = MessageKey.SETUP_Q_POSTCODE
    else:
        _, question_key, _ = _SETUP_STEPS[step - 1]
    client.send_message(
        chat_id=chat_id,
        text=t(question_key, lang, step=step + 1, total=_TOTAL_SETUP_QUESTIONS),
    )


# ---------------------------------------------------------------------------
# Sprint 5C — /tasks, /add_task, /remove_task
# ---------------------------------------------------------------------------

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


def handle_tasks(
    chat_id: int,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Reply with this chat's currently enabled tasks.

    Args:
        chat_id:        Telegram chat to reply to.
        client:         Client used to send the reply.
        settings_store: Store used to load the chat's settings.
        lang:           Display language.
    """
    settings = settings_store.get(chat_id)
    enabled = settings.enabled_tasks if settings is not None else ["laundry"]
    lines = "\n".join(f"  • {_task_display(name)}" for name in enabled)
    client.send_message(chat_id=chat_id, text=t(MessageKey.TASKS_LIST, lang, tasks=lines))


def handle_add_task(
    chat_id: int,
    args: list[str],
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Enable a task type (a ``TASK_REGISTRY`` key) for this chat.

    Args:
        chat_id:        Telegram chat to reply to.
        args:           Command arguments; ``args[0]`` is the task key.
        client:         Client used to send the reply.
        settings_store: Store used to load/persist the chat's settings.
        lang:           Display language.
    """
    if not args:
        client.send_message(chat_id=chat_id, text=t(MessageKey.TASK_USAGE_ADD, lang))
        return

    task_name = args[0].lower()
    if task_name not in TASK_REGISTRY:
        client.send_message(
            chat_id=chat_id,
            text=t(
                MessageKey.TASK_UNKNOWN,
                lang,
                task=task_name,
                valid=", ".join(sorted(TASK_REGISTRY)),
            ),
        )
        return

    settings = settings_store.get(chat_id)
    enabled = list(settings.enabled_tasks) if settings is not None else ["laundry"]
    if task_name in enabled:
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.TASK_ALREADY_ENABLED, lang, task=_task_display(task_name)),
        )
        return

    enabled.append(task_name)
    settings_store.save(_with_enabled_tasks(chat_id, settings, lang, enabled))
    client.send_message(
        chat_id=chat_id, text=t(MessageKey.TASK_ADDED, lang, task=_task_display(task_name))
    )


def handle_remove_task(
    chat_id: int,
    args: list[str],
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore,
    lang: Language,
) -> None:
    """Disable a task type (a ``TASK_REGISTRY`` key) for this chat.

    Args:
        chat_id:        Telegram chat to reply to.
        args:           Command arguments; ``args[0]`` is the task key.
        client:         Client used to send the reply.
        settings_store: Store used to load/persist the chat's settings.
        lang:           Display language.
    """
    if not args:
        client.send_message(chat_id=chat_id, text=t(MessageKey.TASK_USAGE_REMOVE, lang))
        return

    task_name = args[0].lower()
    settings = settings_store.get(chat_id)
    enabled = list(settings.enabled_tasks) if settings is not None else ["laundry"]
    if task_name not in enabled:
        client.send_message(
            chat_id=chat_id,
            text=t(MessageKey.TASK_NOT_ENABLED, lang, task=_task_display(task_name)),
        )
        return

    enabled.remove(task_name)
    settings_store.save(_with_enabled_tasks(chat_id, settings, lang, enabled))
    client.send_message(
        chat_id=chat_id, text=t(MessageKey.TASK_REMOVED, lang, task=_task_display(task_name))
    )


def _with_enabled_tasks(
    chat_id: int, settings: ChatSettings | None, lang: Language, enabled_tasks: list[str]
) -> ChatSettings:
    """Build the next ``ChatSettings`` with ``enabled_tasks`` updated, else unchanged."""
    return ChatSettings(
        chat_id=chat_id,
        language=settings.language if settings is not None else lang,
        profiles=settings.profiles if settings is not None else {},
        onboarding_step=settings.onboarding_step if settings is not None else None,
        enabled_tasks=enabled_tasks,
        onboarding_complete=settings.onboarding_complete if settings is not None else False,
        octopus_region_code=settings.octopus_region_code if settings is not None else None,
        updated_at=utcnow(),
    )


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
