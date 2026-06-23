"""Telegram command handlers.

Each function receives the minimum context it needs and sends exactly one
reply. No business logic beyond formatting the reply text.

Sprint 2A: /health
Sprint 2B: /laundry_done, /events, /summary
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hrse import __version__
from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.utils.datetime_utils import utcnow

if TYPE_CHECKING:
    from hrse.store.protocol import EventStore
    from hrse.telegram.client import TelegramClientProtocol


# ---------------------------------------------------------------------------
# Sprint 2A — unchanged
# ---------------------------------------------------------------------------


def handle_health(chat_id: int, client: TelegramClientProtocol) -> None:
    """Reply to the /health command with a simple status message."""
    text = f"✅ <b>HRSE is healthy</b>\nVersion: <code>{__version__}</code>"
    client.send_message(chat_id=chat_id, text=text)


def handle_unknown(chat_id: int, text: str, client: TelegramClientProtocol) -> None:
    """Reply to any unrecognised command or plain text."""
    reply = (
        "🤖 Unknown command.\n\n"
        "Available commands:\n"
        "  /health — check service status\n"
        "  /laundry_done — record laundry completion\n"
        "  /events — show recent events\n"
        "  /summary — show weekly summary"
    )
    client.send_message(chat_id=chat_id, text=reply)


# ---------------------------------------------------------------------------
# Sprint 2B — event memory commands
# ---------------------------------------------------------------------------


def handle_laundry_done(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
) -> None:
    """Record a laundry completion event and confirm to the user.

    Creates an ``Event(event_type="laundry_completed")`` with the current
    UTC timestamp, persists it via the store, then replies with a
    confirmation that includes the running count for this week.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store to persist the new event.
    """
    from hrse.services.weekly_state import WeeklyStateService

    event = Event(event_type=LAUNDRY_COMPLETED, timestamp=utcnow())
    store.append_event(event)

    summary = WeeklyStateService(store).get_summary()
    text = f"🧺 Laundry recorded.\nThis week: <b>{summary.laundry_count}</b> completed."
    client.send_message(chat_id=chat_id, text=text)


def handle_events(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
) -> None:
    """Reply with up to 10 most recent events, newest first.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store to read events from.
    """
    events = store.list_events()
    recent = list(reversed(events))[:10]  # newest first, max 10

    if not recent:
        client.send_message(chat_id=chat_id, text="📋 No events recorded yet.")
        return

    lines = ["📋 <b>Recent Events</b>"]
    for e in recent:
        ts = e.timestamp.strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"  • {ts} — {e.event_type}")
    client.send_message(chat_id=chat_id, text="\n".join(lines))


def handle_summary(
    chat_id: int,
    client: TelegramClientProtocol,
    store: EventStore,
) -> None:
    """Reply with a weekly summary of household activity.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
        store:   Event store used to build the summary.
    """
    from hrse.services.weekly_state import WeeklyStateService

    summary = WeeklyStateService(store).get_summary()

    last_laundry_str = (
        summary.last_laundry_timestamp.strftime("%Y-%m-%d")
        if summary.last_laundry_timestamp
        else "—"
    )

    text = (
        "🏠 <b>Household Summary</b>\n"
        f"Laundry: <b>{summary.laundry_count}</b> completed\n"
        f"Last Laundry: {last_laundry_str}\n"
        f"Events This Week: <b>{summary.total_events}</b>"
    )
    client.send_message(chat_id=chat_id, text=text)
