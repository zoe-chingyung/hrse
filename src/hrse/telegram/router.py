"""Telegram command router.

The router receives a parsed ``TelegramUpdate``, a ``TelegramClientProtocol``,
and (Sprint 2B+) an ``EventStore``. It dispatches to the correct command
handler and returns nothing.

Sprint 2A commands: /health
Sprint 2B commands: /laundry_done, /events, /summary
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger

from hrse.telegram.commands import (
    handle_events,
    handle_health,
    handle_laundry_done,
    handle_summary,
    handle_unknown,
)

if TYPE_CHECKING:
    from hrse.models.telegram import TelegramUpdate
    from hrse.store.protocol import EventStore
    from hrse.telegram.client import TelegramClientProtocol

logger = Logger(child=True)


def route(
    update: TelegramUpdate,
    client: TelegramClientProtocol,
    store: EventStore | None = None,
) -> None:
    """Dispatch ``update`` to the appropriate command handler.

    Args:
        update: A validated Telegram Update object.
        client: A ``TelegramClientProtocol`` used to send replies.
        store:  An ``EventStore`` for commands that need persistence.
                Optional so that the Sprint 2A /health path is unaffected
                when called without a store (e.g. legacy tests).
    """
    message = update.message
    if message is None:
        logger.warning(
            "Update contains no message; ignoring", extra={"update_id": update.update_id}
        )
        return

    text = (message.text or "").strip()
    chat_id = message.chat.id

    logger.info("Routing command", extra={"chat_id": chat_id, "text": text})

    if text == "/health":
        handle_health(chat_id=chat_id, client=client)

    elif text == "/laundry_done":
        if store is None:
            logger.error("No event store available for /laundry_done")
            client.send_message(chat_id=chat_id, text="⚠️ Service unavailable.")
        else:
            handle_laundry_done(chat_id=chat_id, client=client, store=store)

    elif text == "/events":
        if store is None:
            logger.error("No event store available for /events")
            client.send_message(chat_id=chat_id, text="⚠️ Service unavailable.")
        else:
            handle_events(chat_id=chat_id, client=client, store=store)

    elif text == "/summary":
        if store is None:
            logger.error("No event store available for /summary")
            client.send_message(chat_id=chat_id, text="⚠️ Service unavailable.")
        else:
            handle_summary(chat_id=chat_id, client=client, store=store)

    else:
        handle_unknown(chat_id=chat_id, text=text, client=client)
