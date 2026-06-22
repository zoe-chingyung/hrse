"""Telegram Bot API client.

Design
------
* ``TelegramClientProtocol`` — structural typing contract used throughout the
  codebase and in tests (no concrete dependency required).
* ``HttpTelegramClient`` — production implementation that calls the real
  Telegram Bot API over HTTPS using the standard library ``urllib`` (no extra
  dependency).
* ``get_telegram_client`` — factory that wires the real client with a token
  fetched from AWS Secrets Manager. Call once at Lambda cold-start and reuse.

Dependency injection
--------------------
Handlers accept a ``TelegramClientProtocol`` parameter so tests can pass in
a lightweight mock without touching the network or AWS.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Protocol, runtime_checkable

from aws_lambda_powertools import Logger

from hrse.telegram.token_provider import BotTokenProvider, SecretsManagerTokenProvider

logger = Logger(child=True)

_TELEGRAM_API_BASE = "https://api.telegram.org"


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


@runtime_checkable
class TelegramClientProtocol(Protocol):
    """Structural contract for anything that can send Telegram messages.

    Using a Protocol (instead of ABC) means test doubles just need to
    implement the right methods — no inheritance required.
    """

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> None:
        """Send a text message to ``chat_id``.

        Args:
            chat_id: Telegram chat identifier.
            text:    Message body (HTML or plain text depending on parse_mode).
            parse_mode: Telegram parse mode, defaults to "HTML".

        Raises:
            TelegramApiError: If the Telegram API returns a non-2xx response.
        """
        ...


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class TelegramApiError(Exception):
    """Raised when the Telegram Bot API returns an error response."""

    def __init__(self, status_code: int, description: str) -> None:
        self.status_code = status_code
        self.description = description
        super().__init__(f"Telegram API error {status_code}: {description}")


# ---------------------------------------------------------------------------
# Production implementation
# ---------------------------------------------------------------------------


class HttpTelegramClient:
    """Sends messages to the Telegram Bot API via HTTPS.

    Uses ``urllib`` from the standard library to avoid adding an HTTP client
    dependency (``httpx``, ``requests``, etc.) to the Lambda package.

    Args:
        token_provider: Callable that returns the current bot token string.
                        Passed as a dependency so the token can be refreshed
                        or mocked in tests.
    """

    def __init__(self, token_provider: BotTokenProvider) -> None:
        self._token_provider = token_provider

    # ------------------------------------------------------------------
    # TelegramClientProtocol implementation
    # ------------------------------------------------------------------

    def send_message(self, chat_id: int, text: str, parse_mode: str = "HTML") -> None:
        """POST ``sendMessage`` to the Telegram Bot API.

        Args:
            chat_id:    Telegram chat identifier.
            text:       Message body.
            parse_mode: Telegram parse mode, defaults to "HTML".

        Raises:
            TelegramApiError: If the API returns error JSON or a non-2xx status.
        """
        token = self._token_provider()
        url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": parse_mode}).encode()

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.debug("Sending Telegram message", extra={"chat_id": chat_id})

        try:
            with urllib.request.urlopen(req) as resp:  # noqa: S310  (url is our own constant)
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                body = json.loads(raw)
                description = body.get("description", str(exc))
            except (json.JSONDecodeError, AttributeError):
                description = raw.decode(errors="replace")
            raise TelegramApiError(exc.code, description) from exc

        if not body.get("ok"):
            raise TelegramApiError(
                status_code=body.get("error_code", 0),
                description=body.get("description", "Unknown error"),
            )

        logger.info("Telegram message sent", extra={"chat_id": chat_id})


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_telegram_client() -> HttpTelegramClient:
    """Return a cached ``HttpTelegramClient`` wired with Secrets Manager.

    The token is fetched from Secrets Manager on first call and cached inside
    ``SecretsManagerTokenProvider``. The LRU cache ensures the client itself
    is constructed only once per Lambda container lifetime.

    Call ``get_telegram_client.cache_clear()`` in tests to reset.
    """
    from hrse.config import get_settings

    settings = get_settings()
    token_provider = SecretsManagerTokenProvider(
        secret_name=settings.telegram_secret_name,
        region_name="eu-west-2",
    )
    return HttpTelegramClient(token_provider=token_provider)
