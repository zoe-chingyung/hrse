"""Unit tests for the Telegram command router.

Sprint 2A routes: /health
Sprint 2B routes: /laundry_done, /events, /summary
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hrse.models.telegram import TelegramChat, TelegramMessage, TelegramUpdate, TelegramUser
from hrse.telegram.router import route

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _update(text: str | None, chat_id: int = 1, update_id: int = 1) -> TelegramUpdate:
    return TelegramUpdate(
        update_id=update_id,
        message=TelegramMessage(
            message_id=10,
            chat=TelegramChat(id=chat_id),
            **{"from": TelegramUser(id=42, is_bot=False, first_name="Test")},
            text=text,
        ),
    )


def _empty_update() -> TelegramUpdate:
    return TelegramUpdate(update_id=1, message=None)


def _mock_store() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Sprint 2A routes — unchanged
# ---------------------------------------------------------------------------


class TestRouteSprint2A:
    @patch("hrse.telegram.router.handle_health")
    def test_health_command_dispatches_to_handle_health(self, mock_health: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/health", chat_id=55), client=client)
        mock_health.assert_called_once_with(chat_id=55, client=client)

    @patch("hrse.telegram.router.handle_unknown")
    def test_unknown_command_dispatches_to_handle_unknown(self, mock_unknown: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/bogus", chat_id=7), client=client)
        mock_unknown.assert_called_once_with(chat_id=7, text="/bogus", client=client)

    @patch("hrse.telegram.router.handle_unknown")
    def test_plain_text_dispatches_to_handle_unknown(self, mock_unknown: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("hello world", chat_id=3), client=client)
        mock_unknown.assert_called_once()

    @patch("hrse.telegram.router.handle_health")
    @patch("hrse.telegram.router.handle_unknown")
    def test_no_message_does_not_dispatch(
        self, mock_unknown: MagicMock, mock_health: MagicMock
    ) -> None:
        client = MagicMock()
        route(update=_empty_update(), client=client)
        mock_health.assert_not_called()
        mock_unknown.assert_not_called()

    @patch("hrse.telegram.router.handle_health")
    def test_health_command_with_whitespace_dispatches(self, mock_health: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("  /health  ", chat_id=1), client=client)
        mock_health.assert_called_once()


# ---------------------------------------------------------------------------
# Sprint 2B routes
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestRouteSprint2B:
    @patch("hrse.telegram.router.handle_laundry_done")
    def test_laundry_done_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        store = _mock_store()
        route(update=_update("/laundry_done", chat_id=10), client=client, store=store)
        mock_handler.assert_called_once_with(chat_id=10, client=client, store=store)

    @patch("hrse.telegram.router.handle_events")
    def test_events_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        store = _mock_store()
        route(update=_update("/events", chat_id=20), client=client, store=store)
        mock_handler.assert_called_once_with(chat_id=20, client=client, store=store)

    @patch("hrse.telegram.router.handle_summary")
    def test_summary_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        store = _mock_store()
        route(update=_update("/summary", chat_id=30), client=client, store=store)
        mock_handler.assert_called_once_with(chat_id=30, client=client, store=store)

    def test_store_none_sends_unavailable_for_laundry_done(self) -> None:
        """When no store is provided, the router must gracefully reply."""
        client = MagicMock()
        route(update=_update("/laundry_done"), client=client, store=None)
        client.send_message.assert_called_once()
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower() or "⚠️" in kwargs["text"]

    def test_store_none_sends_unavailable_for_events(self) -> None:
        client = MagicMock()
        route(update=_update("/events"), client=client, store=None)
        client.send_message.assert_called_once()

    def test_store_none_sends_unavailable_for_summary(self) -> None:
        client = MagicMock()
        route(update=_update("/summary"), client=client, store=None)
        client.send_message.assert_called_once()
