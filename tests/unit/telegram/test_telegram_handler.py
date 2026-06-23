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
