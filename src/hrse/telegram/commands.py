"""Telegram command handlers.

Each function receives the minimum context it needs (chat_id + client) and
sends exactly one reply. No business logic beyond formatting the reply text.

Sprint 2A implements /health only. Additional commands land in future sprints.
"""

from __future__ import annotations

from hrse import __version__
from hrse.telegram.client import TelegramClientProtocol


def handle_health(chat_id: int, client: TelegramClientProtocol) -> None:
    """Reply to the /health command with a simple status message.

    Args:
        chat_id: Telegram chat to reply to.
        client:  Client used to send the reply.
    """
    text = f"✅ <b>HRSE is healthy</b>\nVersion: <code>{__version__}</code>"
    client.send_message(chat_id=chat_id, text=text)


def handle_unknown(chat_id: int, text: str, client: TelegramClientProtocol) -> None:
    """Reply to any unrecognised command or plain text.

    Args:
        chat_id: Telegram chat to reply to.
        text:    The original message text (used in the reply for clarity).
        client:  Client used to send the reply.
    """
    reply = (
        "🤖 Unknown command.\n\n"
        "Available commands:\n"
        "  /health — check service status"
    )
    client.send_message(chat_id=chat_id, text=reply)
