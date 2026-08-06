"""Unit tests for Sprint 6 command handlers: onboarding, language, /prices."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from hrse.clients.octopus import OctopusApiError
from hrse.models.chat_settings import ChatSettings, Language
from hrse.models.pricing import PricePoint
from hrse.models.telegram import (
    TelegramCallbackQuery,
    TelegramChat,
    TelegramMessage,
)
from hrse.store.chat_settings_store import InMemoryChatSettingsStore
from hrse.telegram.commands import (
    handle_language_callback,
    handle_language_prompt,
    handle_prices,
    handle_welcome,
)

if TYPE_CHECKING:
    from datetime import datetime as datetime_type

    import pytest

_LONDON = ZoneInfo("Europe/London")


def _mock_client() -> MagicMock:
    return MagicMock()


def _callback(data: str | None, with_message: bool = True) -> TelegramCallbackQuery:
    message = (
        TelegramMessage(message_id=55, chat=TelegramChat(id=-100123)) if with_message else None
    )
    return TelegramCallbackQuery.model_validate(
        {
            "id": "cb-1",
            "from": {"id": 42, "is_bot": False, "first_name": "Zoe"},
            "message": message.model_dump() if message else None,
            "data": data,
        }
    )


class _StubOctopus:
    """Octopus stub that records the requested range and returns canned points."""

    def __init__(self, points: list[PricePoint] | None = None, error: bool = False) -> None:
        self.points = points or []
        self.error = error
        self.period_from: datetime_type | None = None
        self.period_to: datetime_type | None = None

    def get_prices(self, period_from: datetime, period_to: datetime) -> list[PricePoint]:
        if self.error:
            raise OctopusApiError(500, "boom")
        self.period_from = period_from
        self.period_to = period_to
        return self.points


# ---------------------------------------------------------------------------
# handle_welcome / handle_language_prompt
# ---------------------------------------------------------------------------


class TestHandleWelcome:
    def test_sends_bilingual_text_with_language_keyboard(self) -> None:
        client = _mock_client()
        handle_welcome(chat_id=-100123, client=client)

        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == -100123
        assert "Hello" in kwargs["text"]
        assert "你好" in kwargs["text"]
        buttons = kwargs["reply_markup"]["inline_keyboard"][0]
        assert {b["callback_data"] for b in buttons} == {"lang:en", "lang:zh"}


class TestHandleLanguagePrompt:
    def test_sends_prompt_with_keyboard(self) -> None:
        client = _mock_client()
        handle_language_prompt(chat_id=7, client=client)

        _, kwargs = client.send_message.call_args
        assert "請選擇語言" in kwargs["text"]
        assert kwargs["reply_markup"]["inline_keyboard"]


# ---------------------------------------------------------------------------
# handle_language_callback
# ---------------------------------------------------------------------------


class TestHandleLanguageCallback:
    def test_saves_language_answers_and_edits(self) -> None:
        client = _mock_client()
        store = InMemoryChatSettingsStore()

        handle_language_callback(query=_callback("lang:zh"), client=client, settings_store=store)

        saved = store.get(-100123)
        assert saved is not None
        assert saved.language is Language.ZH
        client.answer_callback_query.assert_called_once_with(callback_query_id="cb-1")
        _, kwargs = client.edit_message_text.call_args
        assert kwargs["chat_id"] == -100123
        assert kwargs["message_id"] == 55
        assert "中文" in kwargs["text"]

    def test_confirmation_is_in_chosen_language(self) -> None:
        client = _mock_client()
        store = InMemoryChatSettingsStore()

        handle_language_callback(query=_callback("lang:en"), client=client, settings_store=store)

        _, kwargs = client.edit_message_text.call_args
        assert "English" in kwargs["text"]
        assert "/prices" in kwargs["text"]

    def test_unknown_language_only_answers(self) -> None:
        client = _mock_client()
        store = InMemoryChatSettingsStore()

        handle_language_callback(query=_callback("lang:xx"), client=client, settings_store=store)

        client.answer_callback_query.assert_called_once()
        client.edit_message_text.assert_not_called()
        assert store.get(-100123) is None

    def test_missing_message_only_answers(self) -> None:
        client = _mock_client()
        store = InMemoryChatSettingsStore()

        handle_language_callback(
            query=_callback("lang:en", with_message=False), client=client, settings_store=store
        )

        client.answer_callback_query.assert_called_once()
        client.edit_message_text.assert_not_called()

    def test_selecting_zh_survives_a_store_reload(self) -> None:
        # Regression test: proves the ZH choice made via the language picker
        # is what a later `store.get()` (e.g. from the schedule handler)
        # actually reads back — not silently reset to the English default.
        # Round-trips through JSON to mirror what S3ChatSettingsStore does.
        client = _mock_client()
        store = InMemoryChatSettingsStore()

        handle_language_callback(query=_callback("lang:zh"), client=client, settings_store=store)

        saved = store.get(-100123)
        assert saved is not None
        reloaded = ChatSettings.model_validate_json(saved.model_dump_json())
        assert reloaded.language is Language.ZH


# ---------------------------------------------------------------------------
# handle_prices
# ---------------------------------------------------------------------------


def _half_hourly(start: datetime, prices: list[float]) -> list[PricePoint]:
    return [
        PricePoint(timestamp=start + timedelta(minutes=30 * i), price_pence=p)
        for i, p in enumerate(prices)
    ]


class TestHandlePrices:
    def test_today_queries_local_day_in_utc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 2026-07-12 10:00 UTC == 11:00 BST → local day 2026-07-12
        monkeypatch.setattr(
            "hrse.telegram.commands.utcnow",
            lambda: datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        octopus = _StubOctopus(
            points=_half_hourly(datetime(2026, 7, 11, 23, 0, tzinfo=UTC), [10.0])
        )
        handle_prices(
            chat_id=1,
            client=_mock_client(),
            octopus=octopus,
            lang=Language.EN,
            display_tz=_LONDON,
        )
        # Local midnight 2026-07-12 BST == 23:00 UTC on the 11th.
        assert octopus.period_from == datetime(2026, 7, 11, 23, 0, tzinfo=UTC)
        assert octopus.period_to == datetime(2026, 7, 12, 23, 0, tzinfo=UTC)

    def test_tomorrow_shifts_range_by_one_day(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "hrse.telegram.commands.utcnow",
            lambda: datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        )
        octopus = _StubOctopus(
            points=_half_hourly(datetime(2026, 7, 12, 23, 0, tzinfo=UTC), [10.0])
        )
        handle_prices(
            chat_id=1,
            client=_mock_client(),
            octopus=octopus,
            lang=Language.EN,
            display_tz=_LONDON,
            tomorrow=True,
        )
        assert octopus.period_from == datetime(2026, 7, 12, 23, 0, tzinfo=UTC)
        assert octopus.period_to == datetime(2026, 7, 13, 23, 0, tzinfo=UTC)

    def test_happy_path_sends_header_and_chart(self) -> None:
        client = _mock_client()
        points = _half_hourly(datetime(2026, 7, 11, 23, 0, tzinfo=UTC), [10.0, 5.0, 30.0])
        handle_prices(
            chat_id=9,
            client=client,
            octopus=_StubOctopus(points=points),
            lang=Language.ZH,
            display_tz=_LONDON,
        )
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 9
        assert "今日" in kwargs["text"]
        assert "<pre>" in kwargs["text"]
        assert "最平" in kwargs["text"]

    def test_tomorrow_unpublished_sends_specific_message(self) -> None:
        client = _mock_client()
        handle_prices(
            chat_id=1,
            client=client,
            octopus=_StubOctopus(points=[]),
            lang=Language.EN,
            display_tz=_LONDON,
            tomorrow=True,
        )
        _, kwargs = client.send_message.call_args
        assert "aren't published yet" in kwargs["text"]

    def test_today_empty_sends_generic_unavailable(self) -> None:
        client = _mock_client()
        handle_prices(
            chat_id=1,
            client=client,
            octopus=_StubOctopus(points=[]),
            lang=Language.ZH,
            display_tz=_LONDON,
        )
        _, kwargs = client.send_message.call_args
        assert "攞唔到" in kwargs["text"]

    def test_octopus_error_sends_service_unavailable(self) -> None:
        client = _mock_client()
        handle_prices(
            chat_id=1,
            client=client,
            octopus=_StubOctopus(error=True),
            lang=Language.EN,
            display_tz=_LONDON,
        )
        _, kwargs = client.send_message.call_args
        assert "Service unavailable" in kwargs["text"]
