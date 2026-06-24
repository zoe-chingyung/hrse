"""Unit tests for Sprint 4 notification layer.

Covers:
* SecretsManagerChatIdProvider — happy path, missing key, bad integer, bad JSON
* NotificationService — planning and reminder messages, recommended + not
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from hrse.models.recommendation import Recommendation, RecommendationWindow
from hrse.services.notification import NotificationKind, NotificationService
from hrse.telegram.token_provider import (
    SecretsManagerChatIdProvider,
    get_chat_id_provider,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider(secret: dict[str, str]) -> SecretsManagerChatIdProvider:
    """Build a provider whose boto3 call returns ``secret`` as JSON."""
    import json

    p = SecretsManagerChatIdProvider(secret_name="hrse/dev/telegram", region_name="eu-west-2")
    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {"SecretString": json.dumps(secret)}
    with patch("boto3.client", return_value=mock_client):
        p._fetch_chat_id()  # prime the cache via the real path  # noqa: SLF001
    return p


def _window() -> RecommendationWindow:
    return RecommendationWindow(
        start=datetime(2026, 6, 24, 13, 0, tzinfo=UTC),
        end=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
    )


def _rec_yes() -> Recommendation:
    return Recommendation(
        task="laundry",
        recommended=True,
        window=_window(),
        expected_price_pence=7.5,
        reasons=["laundry target not met", "electricity below threshold (15.0p/kWh)"],
    )


def _rec_no(reason: str = "laundry target already met") -> Recommendation:
    return Recommendation(task="laundry", recommended=False, reasons=[reason])


# ---------------------------------------------------------------------------
# ChatIdProvider tests
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestSecretsManagerChatIdProvider:
    def test_returns_integer_chat_id(self) -> None:
        import json

        p = SecretsManagerChatIdProvider("hrse/dev/telegram")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"bot_token": "tok", "chat_id": "123456789"})
        }
        with patch("boto3.client", return_value=mock_client):
            result = p()
        assert result == 123456789
        assert isinstance(result, int)

    def test_caches_on_second_call(self) -> None:
        import json

        p = SecretsManagerChatIdProvider("hrse/dev/telegram")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": json.dumps({"chat_id": "111"})}
        with patch("boto3.client", return_value=mock_client):
            p()
            p()
        assert mock_client.get_secret_value.call_count == 1

    def test_missing_chat_id_raises_key_error(self) -> None:
        import json

        p = SecretsManagerChatIdProvider("hrse/dev/telegram")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"bot_token": "tok"})
        }
        with (
            patch("boto3.client", return_value=mock_client),
            pytest.raises(KeyError, match="chat_id"),
        ):
            p()

    def test_non_integer_chat_id_raises_value_error(self) -> None:
        import json

        p = SecretsManagerChatIdProvider("hrse/dev/telegram")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {
            "SecretString": json.dumps({"chat_id": "not-a-number"})
        }
        with (
            patch("boto3.client", return_value=mock_client),
            pytest.raises(ValueError, match="not a valid integer"),
        ):
            p()

    def test_invalid_json_raises_value_error(self) -> None:
        p = SecretsManagerChatIdProvider("hrse/dev/telegram")
        mock_client = MagicMock()
        mock_client.get_secret_value.return_value = {"SecretString": "not-json"}
        with (
            patch("boto3.client", return_value=mock_client),
            pytest.raises(ValueError, match="not valid JSON"),
        ):
            p()

    def test_factory_returns_provider(self) -> None:
        get_chat_id_provider.cache_clear()
        provider = get_chat_id_provider()
        assert isinstance(provider, SecretsManagerChatIdProvider)
        get_chat_id_provider.cache_clear()


# ---------------------------------------------------------------------------
# NotificationService — planning messages
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestNotificationServicePlanning:
    def test_recommended_contains_window(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.PLANNING)
        assert "14:00" in msg  # 13:00 UTC = 14:00 BST
        assert "16:00" in msg  # 15:00 UTC = 16:00 BST
        assert "BST" in msg

    def test_recommended_contains_price(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.PLANNING)
        assert "7.5" in msg

    def test_recommended_contains_reasons(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.PLANNING)
        assert "laundry target not met" in msg

    def test_recommended_has_check_marks(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.PLANNING)
        assert "✓" in msg

    def test_not_recommended_says_not_recommended(self) -> None:
        msg = NotificationService().format(_rec_no(), NotificationKind.PLANNING)
        assert "not recommended" in msg.lower()

    def test_not_recommended_contains_reason(self) -> None:
        msg = NotificationService().format(
            _rec_no("rain probability too high"), NotificationKind.PLANNING
        )
        assert "rain probability too high" in msg

    def test_planning_header_present(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.PLANNING)
        assert "Tomorrow" in msg


# ---------------------------------------------------------------------------
# NotificationService — reminder messages
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestNotificationServiceReminder:
    def test_recommended_contains_window(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.REMINDER)
        assert "14:00" in msg  # 13:00 UTC = 14:00 BST
        assert "16:00" in msg  # 15:00 UTC = 16:00 BST
        assert "BST" in msg

    def test_recommended_prompts_laundry_done(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.REMINDER)
        assert "/laundry_done" in msg

    def test_not_recommended_says_no_laundry(self) -> None:
        msg = NotificationService().format(_rec_no(), NotificationKind.REMINDER)
        assert "No laundry" in msg

    def test_reminder_header_present(self) -> None:
        msg = NotificationService().format(_rec_yes(), NotificationKind.REMINDER)
        assert "Reminder" in msg
