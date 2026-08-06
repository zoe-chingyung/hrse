"""Unit tests for the Telegram command router.

Sprint 2A routes: /health
Sprint 2B routes: /laundry_done, /events, /summary
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hrse.models.chat_settings import Language
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
        mock_health.assert_called_once_with(chat_id=55, client=client, lang=Language.EN)

    @patch("hrse.telegram.router.handle_unknown")
    def test_unknown_command_dispatches_to_handle_unknown(self, mock_unknown: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/bogus", chat_id=7), client=client)
        mock_unknown.assert_called_once_with(
            chat_id=7, text="/bogus", client=client, lang=Language.EN
        )

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
        mock_handler.assert_called_once_with(
            chat_id=10, client=client, store=store, lang=Language.EN
        )

    @patch("hrse.telegram.router.handle_events")
    def test_events_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        store = _mock_store()
        route(update=_update("/events", chat_id=20), client=client, store=store)
        mock_handler.assert_called_once_with(
            chat_id=20, client=client, store=store, lang=Language.EN
        )

    @patch("hrse.telegram.router.handle_summary")
    def test_summary_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        store = _mock_store()
        route(update=_update("/summary", chat_id=30), client=client, store=store)
        mock_handler.assert_called_once_with(
            chat_id=30, client=client, store=store, lang=Language.EN
        )

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


# ---------------------------------------------------------------------------
# Sprint 6 — my_chat_member, callback_query, /start, /language, /prices
# ---------------------------------------------------------------------------


def _joined_update(old: str = "left", new: str = "member", chat_id: int = -100) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 5,
            "my_chat_member": {
                "chat": {"id": chat_id},
                "old_chat_member": {"status": old},
                "new_chat_member": {"status": new},
            },
        }
    )


def _callback_update(data: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": 6,
            "callback_query": {
                "id": "cb-9",
                "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
                "message": {"message_id": 3, "chat": {"id": -100}},
                "data": data,
            },
        }
    )


class TestRouteMyChatMember:
    @patch("hrse.telegram.router.handle_welcome")
    def test_bot_added_triggers_welcome(self, mock_welcome: MagicMock) -> None:
        client = MagicMock()
        route(update=_joined_update(), client=client)
        mock_welcome.assert_called_once_with(chat_id=-100, client=client)

    @patch("hrse.telegram.router.handle_welcome")
    def test_bot_promoted_does_not_retrigger_welcome(self, mock_welcome: MagicMock) -> None:
        route(update=_joined_update(old="member", new="administrator"), client=MagicMock())
        mock_welcome.assert_not_called()

    @patch("hrse.telegram.router.handle_welcome")
    def test_bot_removed_is_ignored(self, mock_welcome: MagicMock) -> None:
        route(update=_joined_update(old="member", new="left"), client=MagicMock())
        mock_welcome.assert_not_called()


class TestRouteCallbackQuery:
    @patch("hrse.telegram.router.handle_language_callback")
    def test_language_data_dispatches_to_handler(self, mock_cb: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        update = _callback_update("lang:zh")
        route(update=update, client=client, settings_store=settings_store)
        mock_cb.assert_called_once_with(
            query=update.callback_query, client=client, settings_store=settings_store
        )

    def test_unknown_data_is_answered_and_dropped(self) -> None:
        client = MagicMock()
        route(update=_callback_update("mystery:1"), client=client, settings_store=MagicMock())
        client.answer_callback_query.assert_called_once_with(callback_query_id="cb-9")

    def test_language_data_without_settings_store_is_answered(self) -> None:
        client = MagicMock()
        route(update=_callback_update("lang:en"), client=client)
        client.answer_callback_query.assert_called_once()

    @patch("hrse.telegram.router.handle_region_callback")
    def test_region_data_dispatches_to_handler(self, mock_cb: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        update = _callback_update("region:C")
        route(update=update, client=client, settings_store=settings_store)
        mock_cb.assert_called_once_with(
            query=update.callback_query, client=client, settings_store=settings_store
        )

    def test_region_data_without_settings_store_is_answered(self) -> None:
        client = MagicMock()
        route(update=_callback_update("region:C"), client=client)
        client.answer_callback_query.assert_called_once()


class TestRouteSprint6Commands:
    @patch("hrse.telegram.router.handle_language_prompt")
    def test_language_dispatches_to_prompt(self, mock_prompt: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/language", chat_id=8), client=client)
        mock_prompt.assert_called_once_with(chat_id=8, client=client)

    @patch("hrse.telegram.router.handle_prices")
    def test_prices_defaults_to_today(self, mock_prices: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/prices", chat_id=8), client=client, octopus=MagicMock())
        assert mock_prices.call_args.kwargs["tomorrow"] is False

    @patch("hrse.telegram.router.handle_prices")
    def test_prices_tomorrow_argument(self, mock_prices: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/prices_tomorrow", chat_id=8), client=client, octopus=MagicMock())
        assert mock_prices.call_args.kwargs["tomorrow"] is True

    def test_prices_without_octopus_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/prices", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    @patch("hrse.telegram.router.handle_prices")
    def test_display_timezone_forwarded(self, mock_prices: MagicMock) -> None:
        from zoneinfo import ZoneInfo

        route(
            update=_update("/prices", chat_id=8),
            client=MagicMock(),
            octopus=MagicMock(),
            display_timezone="Asia/Hong_Kong",
        )
        assert mock_prices.call_args.kwargs["display_tz"] == ZoneInfo("Asia/Hong_Kong")


class TestGroupCommandSuffix:
    @patch("hrse.telegram.router.handle_health")
    def test_botname_suffix_is_stripped(self, mock_health: MagicMock) -> None:
        client = MagicMock()
        route(update=_update("/health@HRSEBot", chat_id=55), client=client)
        mock_health.assert_called_once_with(chat_id=55, client=client, lang=Language.EN)

    @patch("hrse.telegram.router.handle_prices")
    def test_suffix_and_args_both_handled(self, mock_prices: MagicMock) -> None:
        route(
            update=_update("/prices@HRSEBot tomorrow", chat_id=5),
            client=MagicMock(),
            octopus=MagicMock(),
        )
        assert mock_prices.call_args.kwargs["tomorrow"] is True


class TestRouteSprint5BCommands:
    @patch("hrse.telegram.router.handle_setup_start")
    def test_setup_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(update=_update("/setup", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8, client=client, settings_store=settings_store, lang=Language.EN
        )

    @patch("hrse.telegram.router.handle_profile")
    def test_profile_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(update=_update("/profile", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8, client=client, settings_store=settings_store, lang=Language.EN
        )

    @patch("hrse.telegram.router.handle_reset")
    def test_reset_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(update=_update("/reset", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8, client=client, settings_store=settings_store, lang=Language.EN
        )

    def test_setup_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/setup", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    def test_profile_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/profile", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    def test_reset_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/reset", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    @patch("hrse.telegram.router.handle_onboarding_answer")
    def test_plain_text_during_onboarding_dispatches_to_answer_handler(
        self, mock_handler: MagicMock
    ) -> None:
        from datetime import UTC, datetime

        from hrse.models.chat_settings import ChatSettings
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        settings_store = InMemoryChatSettingsStore()
        settings_store.save(
            ChatSettings(chat_id=8, onboarding_step=2, updated_at=datetime(2026, 7, 12, tzinfo=UTC))
        )
        client = MagicMock()
        route(update=_update("2 hours", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8,
            text="2 hours",
            client=client,
            settings_store=settings_store,
            lang=Language.EN,
            octopus=None,
        )

    @patch("hrse.telegram.router.handle_onboarding_answer")
    def test_onboarding_answer_forwards_octopus_client(self, mock_handler: MagicMock) -> None:
        from datetime import UTC, datetime

        from hrse.models.chat_settings import ChatSettings
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        settings_store = InMemoryChatSettingsStore()
        settings_store.save(
            ChatSettings(chat_id=8, onboarding_step=0, updated_at=datetime(2026, 7, 12, tzinfo=UTC))
        )
        octopus = MagicMock()
        route(
            update=_update("SW1A 1AA", chat_id=8),
            client=MagicMock(),
            settings_store=settings_store,
            octopus=octopus,
        )
        assert mock_handler.call_args.kwargs["octopus"] is octopus

    @patch("hrse.telegram.router.handle_unknown")
    @patch("hrse.telegram.router.handle_onboarding_answer")
    def test_plain_text_without_onboarding_still_dispatches_to_unknown(
        self, mock_onboarding: MagicMock, mock_unknown: MagicMock
    ) -> None:
        client = MagicMock()
        route(update=_update("hello there"), client=client)
        mock_onboarding.assert_not_called()
        mock_unknown.assert_called_once()

    @patch("hrse.telegram.router.handle_prices")
    def test_prices_prefers_profile_timezone_over_global_default(
        self, mock_prices: MagicMock
    ) -> None:
        from datetime import UTC, datetime
        from zoneinfo import ZoneInfo

        from hrse.models.chat_settings import ChatSettings, TaskProfile
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        settings_store = InMemoryChatSettingsStore()
        settings_store.save(
            ChatSettings(
                chat_id=8,
                profile=TaskProfile(timezone="Asia/Hong_Kong"),
                updated_at=datetime(2026, 7, 12, tzinfo=UTC),
            )
        )
        route(
            update=_update("/prices", chat_id=8),
            client=MagicMock(),
            octopus=MagicMock(),
            settings_store=settings_store,
            display_timezone="Europe/London",
        )
        assert mock_prices.call_args.kwargs["display_tz"] == ZoneInfo("Asia/Hong_Kong")

    @patch("hrse.telegram.router.handle_prices")
    def test_prices_falls_back_to_global_timezone_when_no_profile(
        self, mock_prices: MagicMock
    ) -> None:
        from zoneinfo import ZoneInfo

        route(
            update=_update("/prices", chat_id=8),
            client=MagicMock(),
            octopus=MagicMock(),
            display_timezone="Europe/London",
        )
        assert mock_prices.call_args.kwargs["display_tz"] == ZoneInfo("Europe/London")


class TestRouteSprint5CCommands:
    @patch("hrse.telegram.router.handle_tasks")
    def test_tasks_dispatches_to_handler(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(update=_update("/tasks", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8, client=client, settings_store=settings_store, lang=Language.EN
        )

    @patch("hrse.telegram.router.handle_add_task")
    def test_add_task_dispatches_to_handler_with_args(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(
            update=_update("/add_task dishwasher", chat_id=8),
            client=client,
            settings_store=settings_store,
        )
        mock_handler.assert_called_once_with(
            chat_id=8,
            args=["dishwasher"],
            client=client,
            settings_store=settings_store,
            lang=Language.EN,
        )

    @patch("hrse.telegram.router.handle_remove_task")
    def test_remove_task_dispatches_to_handler_with_args(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(
            update=_update("/remove_task ev", chat_id=8),
            client=client,
            settings_store=settings_store,
        )
        mock_handler.assert_called_once_with(
            chat_id=8, args=["ev"], client=client, settings_store=settings_store, lang=Language.EN
        )

    def test_tasks_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/tasks", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    def test_add_task_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/add_task laundry", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()

    def test_remove_task_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/remove_task laundry", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()


class TestRouteSprintARegistration:
    @patch("hrse.telegram.router.handle_start")
    def test_start_dispatches_to_handler_with_args_and_invite_code(
        self, mock_handler: MagicMock
    ) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(
            update=_update("/start letmein", chat_id=8),
            client=client,
            settings_store=settings_store,
            invite_code="letmein",
        )
        mock_handler.assert_called_once_with(
            chat_id=8,
            args=["letmein"],
            client=client,
            settings_store=settings_store,
            invite_code="letmein",
        )

    @patch("hrse.telegram.router.handle_start")
    def test_start_without_args_dispatches_with_empty_args(self, mock_handler: MagicMock) -> None:
        client = MagicMock()
        settings_store = MagicMock()
        settings_store.get.return_value = None
        route(update=_update("/start", chat_id=8), client=client, settings_store=settings_store)
        mock_handler.assert_called_once_with(
            chat_id=8,
            args=[],
            client=client,
            settings_store=settings_store,
            invite_code="",
        )

    def test_start_without_settings_store_sends_unavailable(self) -> None:
        client = MagicMock()
        route(update=_update("/start letmein", chat_id=8), client=client)
        _, kwargs = client.send_message.call_args
        assert "unavailable" in kwargs["text"].lower()


class TestLanguageResolution:
    @patch("hrse.telegram.router.handle_health")
    def test_stored_language_is_used(self, mock_health: MagicMock) -> None:
        from datetime import UTC, datetime

        from hrse.models.chat_settings import ChatSettings
        from hrse.store.chat_settings_store import InMemoryChatSettingsStore

        settings_store = InMemoryChatSettingsStore()
        settings_store.save(
            ChatSettings(
                chat_id=55, language=Language.ZH, updated_at=datetime(2026, 7, 12, tzinfo=UTC)
            )
        )
        client = MagicMock()
        route(update=_update("/health", chat_id=55), client=client, settings_store=settings_store)
        assert mock_health.call_args.kwargs["lang"] is Language.ZH

    @patch("hrse.telegram.router.handle_health")
    def test_settings_store_failure_defaults_to_english(self, mock_health: MagicMock) -> None:
        broken = MagicMock()
        broken.get.side_effect = RuntimeError("s3 down")
        route(update=_update("/health", chat_id=55), client=MagicMock(), settings_store=broken)
        assert mock_health.call_args.kwargs["lang"] is Language.EN
