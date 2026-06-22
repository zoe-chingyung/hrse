"""Unit tests for the Telegram command router."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hrse.models.telegram import TelegramChat, TelegramMessage, TelegramUpdate, TelegramUser
from hrse.telegram.router import route


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


class TestRoute:
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
        """Leading/trailing whitespace should not break routing."""
        client = MagicMock()
        route(update=_update("  /health  ", chat_id=1), client=client)
        mock_health.assert_called_once()
