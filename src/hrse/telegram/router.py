"""Telegram update router.

The router receives a parsed ``TelegramUpdate`` plus injected dependencies
and dispatches to the correct handler. It understands three update types:

* ``my_chat_member`` — the bot's own membership changed. When the bot has
  just been added to a chat, the bilingual welcome flow starts. This update
  is delivered even with group privacy mode enabled.
* ``callback_query`` — inline-keyboard button presses (language selection).
* ``message`` — slash commands. In groups Telegram appends the bot's
  username (``/summary@MyBot``); the suffix is stripped before matching.
  Plain text from a chat with an active ``/setup`` conversation is routed
  to the onboarding answer handler instead of the unknown-command fallback.

Sprint 2A commands: /health
Sprint 2B commands: /laundry_done, /events, /summary
Sprint 6  commands: /start, /language, /prices [tomorrow]
Sprint 5B commands: /setup, /profile, /reset
Sprint 5C commands: /tasks, /add_task, /remove_task
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from aws_lambda_powertools import Logger

from hrse.models.chat_settings import Language
from hrse.telegram.commands import (
    LANGUAGE_CALLBACK_PREFIX,
    handle_add_task,
    handle_events,
    handle_health,
    handle_language_callback,
    handle_language_prompt,
    handle_laundry_done,
    handle_onboarding_answer,
    handle_prices,
    handle_profile,
    handle_remove_task,
    handle_reset,
    handle_setup_start,
    handle_summary,
    handle_tasks,
    handle_unknown,
    handle_welcome,
)

if TYPE_CHECKING:
    from hrse.clients.octopus import OctopusClientProtocol
    from hrse.models.chat_settings import ChatSettings
    from hrse.models.telegram import TelegramUpdate
    from hrse.store.chat_settings_store import ChatSettingsStore
    from hrse.store.protocol import EventStore
    from hrse.telegram.client import TelegramClientProtocol

logger = Logger(child=True)

# Bot membership statuses meaning "the bot is in the chat".
_JOINED_STATUSES = frozenset({"member", "administrator", "restricted"})
_GONE_STATUSES = frozenset({"left", "kicked"})


def route(
    update: TelegramUpdate,
    client: TelegramClientProtocol,
    store: EventStore | None = None,
    settings_store: ChatSettingsStore | None = None,
    octopus: OctopusClientProtocol | None = None,
    display_timezone: str = "Europe/London",
    window_slots: int = 4,
) -> None:
    """Dispatch ``update`` to the appropriate handler.

    Args:
        update:           A validated Telegram Update object.
        client:           A ``TelegramClientProtocol`` used to send replies.
        store:            An ``EventStore`` for commands that need persistence.
        settings_store:   Per-chat settings store (language). Optional; when
                          absent, replies default to English.
        octopus:          Price client for the /prices command.
        display_timezone: IANA timezone for day boundaries and time display.
        window_slots:     Length of the cheapest /prices window, in 30-min slots.
    """
    if update.my_chat_member is not None:
        _route_my_chat_member(update, client)
        return

    if update.callback_query is not None:
        _route_callback_query(update, client, settings_store)
        return

    if update.message is not None:
        _route_message(
            update, client, store, settings_store, octopus, display_timezone, window_slots
        )
        return

    logger.warning(
        "Update contains no routable payload; ignoring", extra={"update_id": update.update_id}
    )


# ---------------------------------------------------------------------------
# Private routing helpers
# ---------------------------------------------------------------------------


def _route_my_chat_member(update: TelegramUpdate, client: TelegramClientProtocol) -> None:
    """Start the welcome flow when the bot has just been added to a chat."""
    assert update.my_chat_member is not None  # noqa: S101 — narrowing for mypy
    change = update.my_chat_member
    was_out = change.old_chat_member.status in _GONE_STATUSES
    now_in = change.new_chat_member.status in _JOINED_STATUSES

    if was_out and now_in:
        logger.info("Bot added to chat", extra={"chat_id": change.chat.id})
        handle_welcome(chat_id=change.chat.id, client=client)
    else:
        logger.info(
            "Ignoring my_chat_member transition",
            extra={
                "chat_id": change.chat.id,
                "old": change.old_chat_member.status,
                "new": change.new_chat_member.status,
            },
        )


def _route_callback_query(
    update: TelegramUpdate,
    client: TelegramClientProtocol,
    settings_store: ChatSettingsStore | None,
) -> None:
    """Dispatch an inline-keyboard button press."""
    assert update.callback_query is not None  # noqa: S101 — narrowing for mypy
    query = update.callback_query
    data = query.data or ""

    if data.startswith(LANGUAGE_CALLBACK_PREFIX) and settings_store is not None:
        handle_language_callback(query=query, client=client, settings_store=settings_store)
    else:
        logger.warning("Unhandled callback query", extra={"data": data})
        client.answer_callback_query(callback_query_id=query.id)


def _route_message(
    update: TelegramUpdate,
    client: TelegramClientProtocol,
    store: EventStore | None,
    settings_store: ChatSettingsStore | None,
    octopus: OctopusClientProtocol | None,
    display_timezone: str,
    window_slots: int,
) -> None:
    """Parse and dispatch a slash command message.

    ``window_slots`` is the cheapest-window length forwarded to /prices.
    """
    assert update.message is not None  # noqa: S101 — narrowing for mypy
    message = update.message
    text = (message.text or "").strip()
    chat_id = message.chat.id
    chat_settings = _load_chat_settings(chat_id, settings_store)
    lang = chat_settings.language if chat_settings is not None else Language.EN

    command, args = _parse_command(text)
    logger.info("Routing command", extra={"chat_id": chat_id, "command": command})

    if command == "/health":
        handle_health(chat_id=chat_id, client=client, lang=lang)

    elif command == "/start":
        handle_welcome(chat_id=chat_id, client=client)

    elif command == "/language":
        handle_language_prompt(chat_id=chat_id, client=client)

    elif command == "/setup":
        if settings_store is None:
            logger.error("No settings store available for /setup")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_setup_start(
                chat_id=chat_id, client=client, settings_store=settings_store, lang=lang
            )

    elif command == "/profile":
        if settings_store is None:
            logger.error("No settings store available for /profile")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_profile(chat_id=chat_id, client=client, settings_store=settings_store, lang=lang)

    elif command == "/reset":
        if settings_store is None:
            logger.error("No settings store available for /reset")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_reset(chat_id=chat_id, client=client, settings_store=settings_store, lang=lang)

    elif command == "/tasks":
        if settings_store is None:
            logger.error("No settings store available for /tasks")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_tasks(chat_id=chat_id, client=client, settings_store=settings_store, lang=lang)

    elif command == "/add_task":
        if settings_store is None:
            logger.error("No settings store available for /add_task")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_add_task(
                chat_id=chat_id, args=args, client=client, settings_store=settings_store, lang=lang
            )

    elif command == "/remove_task":
        if settings_store is None:
            logger.error("No settings store available for /remove_task")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_remove_task(
                chat_id=chat_id, args=args, client=client, settings_store=settings_store, lang=lang
            )

    elif command in ("/prices", "/prices_tomorrow"):
        if octopus is None:
            logger.error("No Octopus client available for /prices")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_prices(
                chat_id=chat_id,
                client=client,
                octopus=octopus,
                lang=lang,
                display_tz=ZoneInfo(_effective_timezone(chat_settings, display_timezone)),
                window_slots=window_slots,
                tomorrow=command == "/prices_tomorrow"
                or (bool(args) and args[0].lower() == "tomorrow"),
            )

    elif command == "/laundry_done":
        if store is None:
            logger.error("No event store available for /laundry_done")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_laundry_done(chat_id=chat_id, client=client, store=store, lang=lang)

    elif command == "/events":
        if store is None:
            logger.error("No event store available for /events")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_events(chat_id=chat_id, client=client, store=store, lang=lang)

    elif command == "/summary":
        if store is None:
            logger.error("No event store available for /summary")
            _service_unavailable(chat_id, client, lang)
        else:
            handle_summary(chat_id=chat_id, client=client, store=store, lang=lang)

    elif (
        chat_settings is not None
        and chat_settings.onboarding_step is not None
        and settings_store is not None
    ):
        handle_onboarding_answer(
            chat_id=chat_id, text=text, client=client, settings_store=settings_store, lang=lang
        )

    else:
        handle_unknown(chat_id=chat_id, text=text, client=client, lang=lang)


def _parse_command(text: str) -> tuple[str, list[str]]:
    """Split ``text`` into a command and its arguments.

    Strips the ``@botname`` suffix Telegram appends in group chats — the
    webhook only ever receives updates addressed to this bot, so the suffix
    carries no information.

    Args:
        text: The raw message text.

    Returns:
        ``(command, args)``. ``command`` is the first whitespace-separated
        token with any ``@suffix`` removed; ``args`` are remaining tokens.
    """
    parts = text.split()
    if not parts:
        return "", []
    command = parts[0].split("@", 1)[0]
    return command, parts[1:]


def _load_chat_settings(
    chat_id: int, settings_store: ChatSettingsStore | None
) -> ChatSettings | None:
    """Fetch this chat's settings, tolerating a missing store or lookup failure.

    A settings-store failure must never take a command down, so lookup
    errors are logged and ``None`` is returned (callers fall back to English
    / no profile / the global timezone).
    """
    if settings_store is None:
        return None
    try:
        return settings_store.get(chat_id)
    except Exception:
        logger.exception("Failed to load chat settings; using defaults")
        return None


def _effective_timezone(chat_settings: ChatSettings | None, default: str) -> str:
    """Return the chat's preferred profile timezone if set, else the global ``default``.

    Mirrors how ``language`` already prefers the per-chat value (Sprint 5B).
    See ``ChatSettings.effective_timezone`` for the per-task precedence.
    """
    if chat_settings is not None and chat_settings.effective_timezone:
        return chat_settings.effective_timezone
    return default


def _service_unavailable(chat_id: int, client: TelegramClientProtocol, lang: Language) -> None:
    """Send the localized 'service unavailable' reply."""
    from hrse.i18n import MessageKey, t

    client.send_message(chat_id=chat_id, text=t(MessageKey.SERVICE_UNAVAILABLE, lang))
