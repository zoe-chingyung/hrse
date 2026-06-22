"""Unit tests for Telegram command handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

from hrse import __version__
from hrse.telegram.commands import handle_health, handle_unknown


def _mock_client() -> MagicMock:
    return MagicMock()


class TestHandleHealth:
    def test_sends_one_message(self) -> None:
        client = _mock_client()
        handle_health(chat_id=100, client=client)
        client.send_message.assert_called_once()

    def test_sends_to_correct_chat(self) -> None:
        client = _mock_client()
        handle_health(chat_id=999, client=client)
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 999

    def test_reply_contains_healthy(self) -> None:
        client = _mock_client()
        handle_health(chat_id=1, client=client)
        _, kwargs = client.send_message.call_args
        assert "healthy" in kwargs["text"].lower() or "HRSE" in kwargs["text"]

    def test_reply_contains_version(self) -> None:
        client = _mock_client()
        handle_health(chat_id=1, client=client)
        _, kwargs = client.send_message.call_args
        assert __version__ in kwargs["text"]


class TestHandleUnknown:
    def test_sends_one_message(self) -> None:
        client = _mock_client()
        handle_unknown(chat_id=1, text="/bogus", client=client)
        client.send_message.assert_called_once()

    def test_reply_mentions_health_command(self) -> None:
        client = _mock_client()
        handle_unknown(chat_id=1, text="/bogus", client=client)
        _, kwargs = client.send_message.call_args
        assert "/health" in kwargs["text"]
