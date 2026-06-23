"""Unit tests for Telegram command handlers.

Sprint 2A: handle_health, handle_unknown
Sprint 2B: handle_laundry_done, handle_events, handle_summary
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from hrse import __version__
from hrse.models.events import LAUNDRY_COMPLETED, Event
from hrse.telegram.commands import (
    handle_events,
    handle_health,
    handle_laundry_done,
    handle_summary,
    handle_unknown,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_client() -> MagicMock:
    return MagicMock()


def _mock_store(events: list[Event] | None = None) -> MagicMock:
    store = MagicMock()
    store.list_events.return_value = list(events or [])
    return store


def _laundry_event(ts: datetime | None = None) -> Event:
    return Event(
        event_type=LAUNDRY_COMPLETED,
        timestamp=ts or datetime(2026, 6, 23, 12, 0, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# Sprint 2A — handle_health (unchanged)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Sprint 2A — handle_unknown (now lists all commands)
# ---------------------------------------------------------------------------


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

    def test_reply_mentions_new_commands(self) -> None:
        client = _mock_client()
        handle_unknown(chat_id=1, text="/bogus", client=client)
        _, kwargs = client.send_message.call_args
        assert "/laundry_done" in kwargs["text"]
        assert "/events" in kwargs["text"]
        assert "/summary" in kwargs["text"]


# ---------------------------------------------------------------------------
# Sprint 2B — handle_laundry_done
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandleLaundryDone:
    def test_appends_event_to_store(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_laundry_done(chat_id=1, client=client, store=store)
        store.append_event.assert_called_once()

    def test_appended_event_is_laundry_completed(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_laundry_done(chat_id=1, client=client, store=store)
        event = store.append_event.call_args[0][0]
        assert event.event_type == LAUNDRY_COMPLETED

    def test_sends_confirmation_to_correct_chat(self) -> None:
        client = _mock_client()
        store = _mock_store([_laundry_event()])
        handle_laundry_done(chat_id=42, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 42

    def test_reply_contains_laundry_recorded(self) -> None:
        client = _mock_client()
        store = _mock_store([_laundry_event()])
        handle_laundry_done(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "Laundry recorded" in kwargs["text"]

    def test_reply_includes_weekly_count(self) -> None:
        """After appending, the store returns the new event; count should appear."""
        client = _mock_client()
        # After append, list_events returns the new event
        event = _laundry_event()
        store = MagicMock()
        store.list_events.return_value = [event]
        handle_laundry_done(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "1" in kwargs["text"]


# ---------------------------------------------------------------------------
# Sprint 2B — handle_events
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandleEvents:
    def test_sends_one_message(self) -> None:
        client = _mock_client()
        store = _mock_store([_laundry_event()])
        handle_events(chat_id=1, client=client, store=store)
        client.send_message.assert_called_once()

    def test_empty_store_sends_no_events_message(self) -> None:
        client = _mock_client()
        store = _mock_store([])
        handle_events(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "No events" in kwargs["text"]

    def test_event_type_appears_in_reply(self) -> None:
        client = _mock_client()
        store = _mock_store([_laundry_event()])
        handle_events(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert LAUNDRY_COMPLETED in kwargs["text"]

    def test_max_10_events_shown(self) -> None:
        events = [_laundry_event() for _ in range(15)]
        client = _mock_client()
        store = _mock_store(events)
        handle_events(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        # Each event adds one bullet line; 10 lines max
        assert kwargs["text"].count("•") == 10

    def test_sends_to_correct_chat(self) -> None:
        client = _mock_client()
        store = _mock_store([_laundry_event()])
        handle_events(chat_id=77, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 77


# ---------------------------------------------------------------------------
# Sprint 2B — handle_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit()
class TestHandleSummary:
    def test_sends_one_message(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_summary(chat_id=1, client=client, store=store)
        client.send_message.assert_called_once()

    def test_reply_contains_household_summary_header(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_summary(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "Household Summary" in kwargs["text"]

    def test_reply_contains_laundry_count(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_summary(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "Laundry" in kwargs["text"]

    def test_reply_contains_dash_when_no_last_laundry(self) -> None:
        client = _mock_client()
        store = _mock_store([])  # no events
        handle_summary(chat_id=1, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert "—" in kwargs["text"]

    def test_sends_to_correct_chat(self) -> None:
        client = _mock_client()
        store = _mock_store()
        handle_summary(chat_id=55, client=client, store=store)
        _, kwargs = client.send_message.call_args
        assert kwargs["chat_id"] == 55
