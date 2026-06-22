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
The ``_client`` parameter exists solely for testing. Production callers omit
it; the handler resolves the real client from ``get_telegram_client()``.
"""

from __future__ import annotations

import json
from typing import Any

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext
from pydantic import ValidationError

from hrse.models.telegram import TelegramUpdate
from hrse.telegram.client import TelegramClientProtocol, get_telegram_client
from hrse.telegram.router import route

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context(log_event=False)  # False: avoid logging raw token-bearing payloads
@tracer.capture_lambda_handler
def handler(
    event: dict[str, Any],
    context: LambdaContext,
    *,
    _client: TelegramClientProtocol | None = None,
) -> dict[str, Any]:
    """Receive an API Gateway HTTP API event and dispatch to the Telegram router.

    Args:
        event:   API Gateway HTTP API v2 payload.
        context: Lambda runtime context.
        _client: Injected Telegram client (tests only). Production omits this.

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
        # Return 200 so Telegram does not keep retrying a malformed webhook.
        return _ok("invalid payload ignored")

    client = _client if _client is not None else get_telegram_client()

    try:
        route(update=update, client=client)
    except Exception:
        # Log and swallow — never surface 5xx to Telegram or it will retry.
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
