"""Unit tests for Sprint 4 notification layer.

Covers:
* SecretsManagerChatIdProvider — happy path, missing key, bad integer, bad JSON
* NotificationService — planning and reminder messages, recommended + not
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from hrse.models.recommendation import Recommendation, RecommendationWindow
from hrse.services.notification import NotificationKind, NotificationService
from hrse.telegram.token_provider import (
    SecretsManagerChatIdProvider,
    get_chat_id_provider,
)

_LONDON = ZoneInfo("Europe/London")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _service(display_tz: ZoneInfo = _LONDON) -> NotificationService:
    return NotificationService(display_tz=display_tz)


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
        msg = _service().format(_rec_yes(), NotificationKind.PLANNING)
        assert "14:00" in msg  # 13:00 UTC = 14:00 BST
        assert "16:00" in msg  # 15:00 UTC = 16:00 BST
        assert "BST" in msg

    def test_recommended_contains_price(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.PLANNING)
        assert "7.5" in msg

    def test_recommended_contains_reasons(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.PLANNING)
        assert "laundry target not met" in msg

    def test_recommended_has_check_marks(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.PLANNING)
        assert "✓" in msg

    def test_not_recommended_says_not_recommended(self) -> None:
        msg = _service().format(_rec_no(), NotificationKind.PLANNING)
        assert "not recommended" in msg.lower()

    def test_not_recommended_contains_reason(self) -> None:
        msg = _service().format(_rec_no("rain probability too high"), NotificationKind.PLANNING)
        assert "rain probability too high" in msg

    def test_planning_header_present(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.PLANNING)
        assert "Tomorrow" in msg


# ---------------------------------------------------------------------------
# NotificationService — reminder messages
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestNotificationServiceReminder:
    def test_recommended_contains_window(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.REMINDER)
        assert "14:00" in msg  # 13:00 UTC = 14:00 BST
        assert "16:00" in msg  # 15:00 UTC = 16:00 BST
        assert "BST" in msg

    def test_recommended_prompts_laundry_done(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.REMINDER)
        assert "/laundry_done" in msg

    def test_not_recommended_says_no_laundry(self) -> None:
        msg = _service().format(_rec_no(), NotificationKind.REMINDER)
        assert "No laundry" in msg

    def test_reminder_header_present(self) -> None:
        msg = _service().format(_rec_yes(), NotificationKind.REMINDER)
        assert "Reminder" in msg


# ---------------------------------------------------------------------------
# NotificationService — DST-correct timezone label (Phase 0 regression)
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestNotificationServiceTimezoneLabel:
    def test_summer_date_renders_bst(self) -> None:
        rec = Recommendation(
            task="laundry",
            recommended=True,
            window=RecommendationWindow(
                start=datetime(2026, 6, 24, 13, 0, tzinfo=UTC),
                end=datetime(2026, 6, 24, 15, 0, tzinfo=UTC),
            ),
            expected_price_pence=7.5,
            reasons=["laundry target not met"],
        )
        msg = _service().format(rec, NotificationKind.PLANNING)
        assert "BST" in msg
        assert "14:00" in msg  # 13:00 UTC = 14:00 BST

    def test_winter_date_renders_gmt(self) -> None:
        rec = Recommendation(
            task="laundry",
            recommended=True,
            window=RecommendationWindow(
                start=datetime(2026, 12, 24, 13, 0, tzinfo=UTC),
                end=datetime(2026, 12, 24, 15, 0, tzinfo=UTC),
            ),
            expected_price_pence=7.5,
            reasons=["laundry target not met"],
        )
        msg = _service().format(rec, NotificationKind.PLANNING)
        assert "GMT" in msg
        assert "BST" not in msg
        assert "13:00" in msg  # GMT == UTC, no offset

    def test_same_service_instance_handles_both_sides_of_dst(self) -> None:
        # A single NotificationService (one Lambda container) must label
        # each notification correctly regardless of which side of the
        # October/March DST boundary the window falls on.
        svc = _service()
        summer = Recommendation(
            task="laundry",
            recommended=True,
            window=RecommendationWindow(
                start=datetime(2026, 7, 1, 8, 0, tzinfo=UTC),
                end=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
            ),
            reasons=[],
        )
        winter = Recommendation(
            task="laundry",
            recommended=True,
            window=RecommendationWindow(
                start=datetime(2026, 1, 1, 8, 0, tzinfo=UTC),
                end=datetime(2026, 1, 1, 10, 0, tzinfo=UTC),
            ),
            reasons=[],
        )
        assert "BST" in svc.format(summer, NotificationKind.REMINDER)
        assert "GMT" in svc.format(winter, NotificationKind.REMINDER)


# ---------------------------------------------------------------------------
# NotificationService.format_multi — Sprint 5C multi-task messages
# ---------------------------------------------------------------------------


def _dishwasher_rec(recommended: bool = True) -> Recommendation:
    if not recommended:
        return Recommendation(task="dishwasher", recommended=False, reasons=["target already met"])
    return Recommendation(
        task="dishwasher",
        recommended=True,
        window=RecommendationWindow(
            start=datetime(2026, 6, 24, 9, 0, tzinfo=UTC),
            end=datetime(2026, 6, 24, 10, 30, tzinfo=UTC),
        ),
        expected_price_pence=5.0,
        reasons=["cost within budget"],
    )


@pytest.mark.unit()
class TestFormatMultiSingleTaskRegression:
    """A single recommendation must render byte-identical to format()."""

    def test_single_recommendation_planning_matches_format(self) -> None:
        svc = _service()
        rec = _rec_yes()
        assert svc.format_multi([rec], NotificationKind.PLANNING) == svc.format(
            rec, NotificationKind.PLANNING
        )

    def test_single_recommendation_reminder_matches_format(self) -> None:
        svc = _service()
        rec = _rec_yes()
        assert svc.format_multi([rec], NotificationKind.REMINDER) == svc.format(
            rec, NotificationKind.REMINDER
        )

    def test_single_not_recommended_matches_format(self) -> None:
        svc = _service()
        rec = _rec_no()
        assert svc.format_multi([rec], NotificationKind.PLANNING) == svc.format(
            rec, NotificationKind.PLANNING
        )


@pytest.mark.unit()
class TestFormatMultiMultipleTasks:
    def test_raises_on_empty_list(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            _service().format_multi([], NotificationKind.PLANNING)

    def test_planning_has_one_block_per_task(self) -> None:
        text = _service().format_multi([_rec_yes(), _dishwasher_rec()], NotificationKind.PLANNING)
        assert "Laundry" in text
        assert "Dishwasher" in text

    def test_planning_keeps_overall_header(self) -> None:
        text = _service().format_multi([_rec_yes(), _dishwasher_rec()], NotificationKind.PLANNING)
        assert "Tomorrow's Energy Plan" in text

    def test_reminder_has_one_block_per_task(self) -> None:
        text = _service().format_multi([_rec_yes(), _dishwasher_rec()], NotificationKind.REMINDER)
        assert "Laundry" in text
        assert "Dishwasher" in text
        assert "Morning Reminder" in text

    def test_not_recommended_task_shows_in_its_own_block(self) -> None:
        text = _service().format_multi(
            [_rec_yes(), _dishwasher_rec(recommended=False)], NotificationKind.PLANNING
        )
        assert "target already met" in text

    def test_laundry_done_prompt_only_on_laundry_block(self) -> None:
        text = _service().format_multi([_rec_yes(), _dishwasher_rec()], NotificationKind.REMINDER)
        assert text.count("/laundry_done") == 1

    def test_unmapped_task_name_falls_back_to_title_case_label(self) -> None:
        rec = Recommendation(task="gardening", recommended=False, reasons=["r"])
        text = _service().format_multi([_rec_yes(), rec], NotificationKind.PLANNING)
        assert "Gardening" in text

    def test_ev_charging_uses_its_mapped_label(self) -> None:
        rec = Recommendation(task="ev_charging", recommended=False, reasons=["r"])
        text = _service().format_multi([_rec_yes(), rec], NotificationKind.PLANNING)
        assert "EV Charging" in text
