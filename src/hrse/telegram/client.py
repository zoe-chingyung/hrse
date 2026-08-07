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
from typing import Any, Protocol, runtime_checkable

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

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Send a text message to ``chat_id``.

        Args:
            chat_id: Telegram chat identifier.
            text:    Message body (HTML or plain text depending on parse_mode).
            parse_mode: Telegram parse mode, defaults to "HTML".
            reply_markup: Optional InlineKeyboardMarkup as a plain dict.

        Raises:
            TelegramApiError: If the Telegram API returns a non-2xx response.
        """
        ...

    def answer_callback_query(self, callback_query_id: str) -> None:
        """Acknowledge an inline-keyboard button press (stops the spinner).

        Args:
            callback_query_id: The ``id`` field of the CallbackQuery.

        Raises:
            TelegramApiError: If the Telegram API returns a non-2xx response.
        """
        ...

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """Replace the text of an existing bot message.

        Omitting ``reply_markup`` also removes any inline keyboard the
        message had; passing one (e.g. an updated multi-select checklist)
        keeps the message interactive.

        Args:
            chat_id:    Telegram chat identifier.
            message_id: Identifier of the message to edit.
            text:       New message body.
            parse_mode: Telegram parse mode, defaults to "HTML".
            reply_markup: Optional InlineKeyboardMarkup as a plain dict.

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

    def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """POST ``sendMessage`` to the Telegram Bot API.

        Args:
            chat_id:    Telegram chat identifier.
            text:       Message body.
            parse_mode: Telegram parse mode, defaults to "HTML".
            reply_markup: Optional InlineKeyboardMarkup as a plain dict.

        Raises:
            TelegramApiError: If the API returns error JSON or a non-2xx status.
        """
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self._post("sendMessage", payload)
        logger.info("Telegram message sent", extra={"chat_id": chat_id})

    def answer_callback_query(self, callback_query_id: str) -> None:
        """POST ``answerCallbackQuery`` to acknowledge a button press.

        Args:
            callback_query_id: The ``id`` field of the CallbackQuery.

        Raises:
            TelegramApiError: If the API returns error JSON or a non-2xx status.
        """
        self._post("answerCallbackQuery", {"callback_query_id": callback_query_id})
        logger.debug("Callback query answered", extra={"callback_query_id": callback_query_id})

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: dict[str, Any] | None = None,
    ) -> None:
        """POST ``editMessageText`` to replace an existing message's body.

        Editing without ``reply_markup`` also removes any inline keyboard,
        which is what a locked-in onboarding choice wants. Passing one keeps
        the message interactive (e.g. an updated multi-select checklist).

        Args:
            chat_id:    Telegram chat identifier.
            message_id: Identifier of the message to edit.
            text:       New message body.
            parse_mode: Telegram parse mode, defaults to "HTML".
            reply_markup: Optional InlineKeyboardMarkup as a plain dict.

        Raises:
            TelegramApiError: If the API returns error JSON or a non-2xx status.
        """
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        self._post("editMessageText", payload)
        logger.info("Telegram message edited", extra={"chat_id": chat_id})

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _post(self, method: str, payload: dict[str, Any]) -> None:
        """POST ``payload`` to a Bot API ``method``, raising on any error.

        Args:
            method:  Bot API method name, e.g. "sendMessage".
            payload: JSON-serialisable request body.

        Raises:
            TelegramApiError: If the API returns error JSON or a non-2xx status.
        """
        token = self._token_provider()
        url = f"{_TELEGRAM_API_BASE}/bot{token}/{method}"
        body_bytes = json.dumps(payload).encode()

        req = urllib.request.Request(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.debug("Calling Telegram API", extra={"method": method})

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
