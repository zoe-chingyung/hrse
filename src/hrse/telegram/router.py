"""Telegram command router.

The router receives a parsed ``TelegramUpdate`` and a ``TelegramClientProtocol``
instance, dispatches to the correct command handler, and returns nothing.

Adding a new command in future sprints means adding one ``elif`` branch here
(or replacing with a dict-based dispatch table once commands grow).

No business logic lives here beyond routing — command handlers are responsible
for building the reply text.
"""

from __future__ import annotations

from aws_lambda_powertools import Logger

from hrse.models.telegram import TelegramUpdate
from hrse.telegram.client import TelegramClientProtocol
from hrse.telegram.commands import handle_health, handle_unknown

logger = Logger(child=True)


def route(update: TelegramUpdate, client: TelegramClientProtocol) -> None:
    """Dispatch ``update`` to the appropriate command handler.

    Args:
        update: A validated Telegram Update object.
        client: A ``TelegramClientProtocol`` used to send replies.
    """
    message = update.message
    if message is None:
        logger.warning("Update contains no message; ignoring", extra={"update_id": update.update_id})
        return

    text = (message.text or "").strip()
    chat_id = message.chat.id

    logger.info("Routing command", extra={"chat_id": chat_id, "text": text})

    if text == "/health":
        handle_health(chat_id=chat_id, client=client)
    else:
        handle_unknown(chat_id=chat_id, text=text, client=client)
