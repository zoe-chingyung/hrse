"""Lambda handler for Telegram webhook events.

Entry point: ``hrse.handlers.telegram_handler.handler``

Invocation path
---------------
Telegram → HTTPS POST → API Gateway HTTP API → Lambda

The handler is intentionally thin:
1. Parse the raw API Gateway payload into a ``TelegramUpdate``.
2. Delegate to ``router.route()``.
3. Return HTTP 200 — Telegram retries on non-2xx, so we always acknowledge
   receipt even when the command fails (errors are logged, not re-raised).

Dependency injection
--------------------
``_client`` and ``_store`` are keyword-only parameters accepted for testing.
Production callers omit them; the handler resolves real instances from the
LRU-cached factories.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from aws_lambda_powertools import Logger, Tracer
from pydantic import ValidationError

from hrse.models.telegram import TelegramUpdate
from hrse.store.s3_store import get_event_store
from hrse.telegram.client import TelegramClientProtocol, get_telegram_client
from hrse.telegram.router import route

if TYPE_CHECKING:
    from aws_lambda_powertools.utilities.typing import LambdaContext
    from hrse.store.protocol import EventStore

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=False)  # False: avoid logging raw token-bearing payloads
@tracer.capture_lambda_handler
def handler(
    event: dict[str, Any],
    context: LambdaContext,
    *,
    _client: TelegramClientProtocol | None = None,
    _store: EventStore | None = None,
) -> dict[str, Any]:
    """Receive an API Gateway HTTP API event and dispatch to the Telegram router.

    Args:
        event:   API Gateway HTTP API v2 payload.
        context: Lambda runtime context.
        _client: Injected Telegram client (tests only). Production omits this.
        _store:  Injected event store (tests only). Production omits this.

    Returns:
        API Gateway-compatible response with ``statusCode`` 200.
        Telegram expects 200 on every response — errors are logged internally.
    """
    body_raw: str = event.get("body") or "{}"

    try:
        payload = json.loads(body_raw)
        update = TelegramUpdate.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as exc:
        logger.warning("Invalid Telegram update payload", extra={"error": str(exc)})
        return _ok("invalid payload ignored")

    client = _client if _client is not None else get_telegram_client()
    store = _store if _store is not None else get_event_store()

    try:
        route(update=update, client=client, store=store)
    except Exception:
        logger.exception("Unhandled error while processing Telegram update")

    return _ok("ok")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(message: str) -> dict[str, Any]:
    """Build a minimal 200 API Gateway response."""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"ok": True, "message": message}),
    }
