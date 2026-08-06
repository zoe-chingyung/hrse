"""Unit tests for the Telegram Lambda handler."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from hrse.handlers.telegram_handler import handler

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _context() -> MagicMock:
    ctx = MagicMock()
    ctx.function_name = "hrse-telegram-handler"
    ctx.aws_request_id = "test-req-id"
    ctx.invoked_function_arn = "arn:aws:lambda:eu-west-2:123456789012:function:hrse-telegram"
    return ctx


def _apigw_event(body: dict | None = None, raw_body: str | None = None) -> dict:
    """Build a minimal API Gateway HTTP API v2 event."""
    serialised = raw_body if raw_body is not None else json.dumps(body or {})
    return {
        "version": "2.0",
        "routeKey": "POST /webhook",
        "rawPath": "/webhook",
        "body": serialised,
        "headers": {"content-type": "application/json"},
        "requestContext": {"http": {"method": "POST"}},
    }


def _health_update(chat_id: int = 100) -> dict:
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id},
            "from": {"id": 42, "is_bot": False, "first_name": "Test"},
            "text": "/health",
        },
    }


# ---------------------------------------------------------------------------
# Always-200 contract
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandlerAlways200:
    def test_returns_200_on_valid_update(self) -> None:
        client = MagicMock()
        response = handler(_apigw_event(_health_update()), _context(), _client=client)
        assert response["statusCode"] == 200

    def test_returns_200_on_invalid_json(self) -> None:
        response = handler(_apigw_event(raw_body="not-json"), _context())
        assert response["statusCode"] == 200

    def test_returns_200_on_empty_body(self) -> None:
        response = handler(_apigw_event(raw_body=""), _context())
        assert response["statusCode"] == 200

    def test_returns_200_when_client_raises(self) -> None:
        client = MagicMock()
        client.send_message.side_effect = RuntimeError("network failure")
        response = handler(_apigw_event(_health_update()), _context(), _client=client)
        assert response["statusCode"] == 200

    def test_body_is_valid_json(self) -> None:
        client = MagicMock()
        response = handler(_apigw_event(_health_update()), _context(), _client=client)
        body = json.loads(response["body"])
        assert "ok" in body


# ---------------------------------------------------------------------------
# Routing via injected client
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandlerRouting:
    def test_health_command_calls_send_message(self) -> None:
        client = MagicMock()
        handler(_apigw_event(_health_update(chat_id=77)), _context(), _client=client)
        client.send_message.assert_called_once()
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 77

    def test_no_message_field_does_not_call_send_message(self) -> None:
        client = MagicMock()
        handler(_apigw_event({"update_id": 1}), _context(), _client=client)
        client.send_message.assert_not_called()

    def test_missing_body_key_does_not_raise(self) -> None:
        """If 'body' key is absent the handler must still return 200."""
        client = MagicMock()
        event: dict = {}  # no 'body' key at all
        response = handler(event, _context(), _client=client)
        assert response["statusCode"] == 200


# ---------------------------------------------------------------------------
# Dependency injection: production client resolution
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandlerClientResolution:
    def test_uses_injected_client_when_provided(self) -> None:
        client = MagicMock()
        with patch("hrse.handlers.telegram_handler.get_telegram_client") as mock_factory:
            handler(_apigw_event(_health_update()), _context(), _client=client)
            # Factory must NOT be called when a client is injected.
            mock_factory.assert_not_called()

    def test_calls_factory_when_no_client_injected(self) -> None:
        mock_client = MagicMock()
        with patch(
            "hrse.handlers.telegram_handler.get_telegram_client",
            return_value=mock_client,
        ):
            response = handler(_apigw_event(_health_update()), _context())
            assert response["statusCode"] == 200


# ---------------------------------------------------------------------------
# Sprint 6 — end-to-end wiring through the handler
# ---------------------------------------------------------------------------


class TestSprint6Wiring:
    def test_my_chat_member_join_sends_welcome_with_keyboard(self) -> None:
        from unittest.mock import MagicMock

        client = MagicMock()
        event = {
            "body": json.dumps(
                {
                    "update_id": 1,
                    "my_chat_member": {
                        "chat": {"id": -100123},
                        "old_chat_member": {"status": "left"},
                        "new_chat_member": {"status": "member"},
                    },
                }
            )
        }
        response = handler(
            event,
            _context(),
            _client=client,
            _store=MagicMock(),
            _settings_store=MagicMock(),
            _octopus=MagicMock(),
        )
        assert response["statusCode"] == 200
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == -100123
        assert kwargs["reply_markup"] is not None

    def test_language_callback_persists_choice(self) -> None:
        from unittest.mock import MagicMock

        from hrse.models.chat_settings import Language
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        client = MagicMock()
        settings_store = InMemoryChatSettingsStore()
        event = {
            "body": json.dumps(
                {
                    "update_id": 2,
                    "callback_query": {
                        "id": "cb-1",
                        "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                        "message": {"message_id": 5, "chat": {"id": -100123}},
                        "data": "lang:zh",
                    },
                }
            )
        }
        response = handler(
            event,
            _context(),
            _client=client,
            _store=MagicMock(),
            _settings_store=settings_store,
            _octopus=MagicMock(),
        )
        assert response["statusCode"] == 200
        saved = settings_store.get(-100123)
        assert saved is not None
        assert saved.language is Language.ZH


# ---------------------------------------------------------------------------
# Sprint A — invite_code resolved from Settings and forwarded to the router
# ---------------------------------------------------------------------------


class TestSprintAInviteCodeWiring:
    def _start_event(self, text: str, chat_id: int = -100123) -> dict:
        return {
            "body": json.dumps(
                {
                    "update_id": 3,
                    "message": {
                        "message_id": 1,
                        "chat": {"id": chat_id},
                        "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                        "text": text,
                    },
                }
            )
        }

    def test_correct_invite_code_registers_chat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        monkeypatch.setenv("HRSE_INVITE_CODE", "letmein")
        client = MagicMock()
        settings_store = InMemoryChatSettingsStore()
        response = handler(
            self._start_event("/start letmein"),
            _context(),
            _client=client,
            _store=MagicMock(),
            _settings_store=settings_store,
            _octopus=MagicMock(),
        )
        assert response["statusCode"] == 200
        saved = settings_store.get(-100123)
        assert saved is not None
        assert saved.onboarding_complete is False

    def test_wrong_invite_code_does_not_register_chat(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        monkeypatch.setenv("HRSE_INVITE_CODE", "letmein")
        client = MagicMock()
        settings_store = InMemoryChatSettingsStore()
        response = handler(
            self._start_event("/start wrongcode"),
            _context(),
            _client=client,
            _store=MagicMock(),
            _settings_store=settings_store,
            _octopus=MagicMock(),
        )
        assert response["statusCode"] == 200
        assert settings_store.get(-100123) is None
