"""Unit tests for HttpTelegramClient."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from hrse.telegram.client import HttpTelegramClient, TelegramApiError, TelegramClientProtocol

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_client(token: str = "test-token") -> HttpTelegramClient:
    return HttpTelegramClient(token_provider=lambda: token)


def _mock_response(body: dict) -> MagicMock:
    """Build a mock HTTP response that behaves like urllib's response."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(body).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ---------------------------------------------------------------------------
# Protocol compliance
# ---------------------------------------------------------------------------


class TestProtocolCompliance:
    def test_http_client_satisfies_protocol(self) -> None:
        client = _make_client()
        assert isinstance(client, TelegramClientProtocol)


# ---------------------------------------------------------------------------
# send_message happy path
# ---------------------------------------------------------------------------


class TestSendMessage:
    @patch("urllib.request.urlopen")
    def test_calls_correct_url(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        client = _make_client(token="my-token")
        client.send_message(chat_id=123, text="hello")

        call_args = mock_urlopen.call_args
        req = call_args[0][0]
        assert "/botmy-token/sendMessage" in req.full_url

    @patch("urllib.request.urlopen")
    def test_sends_correct_payload(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        client = _make_client()
        client.send_message(chat_id=42, text="test message", parse_mode="Markdown")

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["chat_id"] == 42
        assert body["text"] == "test message"
        assert body["parse_mode"] == "Markdown"

    @patch("urllib.request.urlopen")
    def test_default_parse_mode_is_html(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        client = _make_client()
        client.send_message(chat_id=1, text="hi")

        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data)
        assert body["parse_mode"] == "HTML"

    @patch("urllib.request.urlopen")
    def test_uses_post_method(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        client = _make_client()
        client.send_message(chat_id=1, text="hi")

        req = mock_urlopen.call_args[0][0]
        assert req.method == "POST"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestSendMessageErrors:
    @patch("urllib.request.urlopen")
    def test_api_ok_false_raises_telegram_api_error(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"ok": False, "error_code": 400, "description": "Bad Request"}
        )
        client = _make_client()
        with pytest.raises(TelegramApiError) as exc_info:
            client.send_message(chat_id=1, text="hi")
        assert exc_info.value.status_code == 400
        assert "Bad Request" in str(exc_info.value)

    @patch("urllib.request.urlopen")
    def test_http_error_raises_telegram_api_error(self, mock_urlopen: MagicMock) -> None:
        error_body = json.dumps({"description": "Unauthorized"}).encode()
        http_error = urllib.error.HTTPError(
            url="https://api.telegram.org",
            code=401,
            msg="Unauthorized",
            hdrs=MagicMock(),  # type: ignore[arg-type]
            fp=BytesIO(error_body),
        )
        mock_urlopen.side_effect = http_error
        client = _make_client()
        with pytest.raises(TelegramApiError) as exc_info:
            client.send_message(chat_id=1, text="hi")
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Sprint 6 — reply_markup, answerCallbackQuery, editMessageText
# ---------------------------------------------------------------------------


class TestSendMessageReplyMarkup:
    @patch("urllib.request.urlopen")
    def test_reply_markup_included_when_provided(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        markup = {"inline_keyboard": [[{"text": "English", "callback_data": "lang:en"}]]}
        _make_client().send_message(chat_id=1, text="hi", reply_markup=markup)

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["reply_markup"] == markup

    @patch("urllib.request.urlopen")
    def test_reply_markup_omitted_by_default(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        _make_client().send_message(chat_id=1, text="hi")

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "reply_markup" not in body


class TestAnswerCallbackQuery:
    @patch("urllib.request.urlopen")
    def test_calls_correct_url_and_payload(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": True})
        _make_client(token="tok").answer_callback_query(callback_query_id="cb-77")

        req = mock_urlopen.call_args[0][0]
        assert "/bottok/answerCallbackQuery" in req.full_url
        assert json.loads(req.data) == {"callback_query_id": "cb-77"}

    @patch("urllib.request.urlopen")
    def test_api_error_raises(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response(
            {"ok": False, "error_code": 400, "description": "query is too old"}
        )
        with pytest.raises(TelegramApiError, match="query is too old"):
            _make_client().answer_callback_query(callback_query_id="stale")


class TestEditMessageText:
    @patch("urllib.request.urlopen")
    def test_calls_correct_url_and_payload(self, mock_urlopen: MagicMock) -> None:
        mock_urlopen.return_value = _mock_response({"ok": True, "result": {}})
        _make_client(token="tok").edit_message_text(chat_id=-5, message_id=9, text="done")

        req = mock_urlopen.call_args[0][0]
        assert "/bottok/editMessageText" in req.full_url
        body = json.loads(req.data)
        assert body == {"chat_id": -5, "message_id": 9, "text": "done", "parse_mode": "HTML"}

    @patch("urllib.request.urlopen")
    def test_http_error_raises_telegram_api_error(self, mock_urlopen: MagicMock) -> None:
        error_body = json.dumps({"description": "message not found"}).encode()
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="x", code=400, msg="Bad Request", hdrs=None, fp=BytesIO(error_body)
        )
        with pytest.raises(TelegramApiError, match="message not found"):
            _make_client().edit_message_text(chat_id=1, message_id=1, text="x")
