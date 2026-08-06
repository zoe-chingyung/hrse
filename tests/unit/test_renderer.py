"""Unit tests for the price bar chart rendering service.

Pure presentation logic — no AWS, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hrse.models.chat_settings import ChatSettings, Language
from hrse.models.pricing import PriceSlot
from hrse.services import renderer as renderer_module
from hrse.services.renderer import render_price_bar_chart

_NOW = datetime(2026, 7, 12, tzinfo=UTC)
_UTC_MIDNIGHT = datetime(2026, 7, 11, 23, 0, tzinfo=UTC)  # 00:00 BST on 2026-07-12


def _settings(**overrides: object) -> ChatSettings:
    return ChatSettings(chat_id=1, updated_at=_NOW, **overrides)  # type: ignore[arg-type]


def _slots(prices: list[float]) -> list[PriceSlot]:
    """Build consecutive half-hour PriceSlots starting at local midnight."""
    return [
        PriceSlot(timestamp=_UTC_MIDNIGHT + timedelta(minutes=30 * i), price_pence=p)
        for i, p in enumerate(prices)
    ]


def _body(text: str) -> str:
    """Strip the ``` fence and return the inner message body."""
    assert text.startswith("```\n")
    assert text.endswith("\n```")
    return text[len("```\n") : -len("\n```")]


def _rows(text: str) -> list[str]:
    """Return just the cheap-section bar rows (between the title and footer blanks).

    Uses the first two blank lines specifically (not the last) since an
    optional avoid-list section — with its own leading blank line — may
    follow the footer.
    """
    lines = _body(text).splitlines()
    blank_indices = [i for i, line in enumerate(lines) if line == ""]
    start, end = blank_indices[0] + 1, blank_indices[1]
    return lines[start:end]


def _avoid_section(text: str) -> list[str]:
    """Return the avoid-list price rows (after the ⚠️ header), or [] if absent.

    Excludes a trailing "…" truncation-marker line, if present, so callers
    get just the actual rows.
    """
    lines = _body(text).splitlines()
    for i, line in enumerate(lines):
        if line.startswith("⚠️"):  # ⚠️
            rows = lines[i + 1 :]
            return [row for row in rows if row != "…"]
    return []


class TestSortOrder:
    def test_rows_ascend_by_price(self) -> None:
        slots = _slots([21.4, 5.3, 28.9, 15.1])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        prices = [float(row.split("p")[0].split()[-1]) for row in rows]
        assert prices == sorted(prices)

    def test_input_order_does_not_matter(self) -> None:
        slots = _slots([5.3, 15.1, 28.9])
        reordered = [slots[2], slots[0], slots[1]]
        assert render_price_bar_chart(slots, _settings()) == render_price_bar_chart(
            reordered, _settings()
        )


class TestColourTiers:
    def test_default_thresholds_green_yellow_red(self) -> None:
        # Defaults: green < 10p, 10p <= yellow <= 20p, red > 20p.
        slots = _slots([5.3, 15.1, 28.9])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert rows[0].startswith("\U0001f7e2")  # 5.3p -> green
        assert rows[1].startswith("\U0001f7e1")  # 15.1p -> yellow
        assert rows[2].startswith("\U0001f534")  # 28.9p -> red

    def test_boundary_equal_to_green_threshold_is_yellow(self) -> None:
        settings = _settings(chart_green_threshold_pence=10.0, chart_red_threshold_pence=20.0)
        rows = _rows(render_price_bar_chart(_slots([10.0]), settings))
        assert rows[0].startswith("\U0001f7e1")  # exactly at green boundary -> not green

    def test_boundary_equal_to_red_threshold_is_yellow(self) -> None:
        settings = _settings(chart_green_threshold_pence=10.0, chart_red_threshold_pence=20.0)
        rows = _rows(render_price_bar_chart(_slots([20.0]), settings))
        assert rows[0].startswith("\U0001f7e1")  # exactly at red boundary -> still yellow

    def test_just_above_red_threshold_is_red(self) -> None:
        settings = _settings(chart_green_threshold_pence=10.0, chart_red_threshold_pence=20.0)
        rows = _rows(render_price_bar_chart(_slots([20.01]), settings))
        assert rows[0].startswith("\U0001f534")

    def test_thresholds_are_configurable_not_hardcoded(self) -> None:
        # With a green threshold of 30p, a 15.1p slot that would normally be
        # yellow must render green instead — proves it's read from settings.
        settings = _settings(chart_green_threshold_pence=30.0, chart_red_threshold_pence=40.0)
        rows = _rows(render_price_bar_chart(_slots([15.1]), settings))
        assert rows[0].startswith("\U0001f7e2")


class TestBarLength:
    def test_cheapest_and_most_expensive_bar_lengths(self) -> None:
        # max_price = 28.9; expect round(5.3/28.9*8)=1, round(28.9/28.9*8)=8.
        slots = _slots([5.3, 28.9])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert rows[0].count("▇") == 1
        assert rows[1].count("▇") == 8

    def test_matches_worked_example(self) -> None:
        slots = _slots([5.3, 8.2, 15.1, 19.7, 21.4, 28.9])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        bar_counts = [row.count("▇") for row in rows]
        assert bar_counts == [1, 2, 4, 5, 6, 8]

    def test_floor_of_one_cell_even_for_tiny_fraction(self) -> None:
        # A near-zero price against a large max would round to 0 without the floor.
        slots = _slots([0.01, 1000.0])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert rows[0].count("▇") >= 1

    def test_all_zero_prices_do_not_crash_and_floor_to_one(self) -> None:
        slots = _slots([0.0, 0.0])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert all(row.count("▇") == 1 for row in rows)


class TestNegativePriceBaseline:
    def test_negative_price_floors_to_one_cell_not_negative(self) -> None:
        slots = _slots([-5.0, 20.0])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert rows[0].count("▇") == 1  # baseline from 0, never negative-width

    def test_negative_price_still_tiered_green(self) -> None:
        slots = _slots([-5.0, 20.0])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert rows[0].startswith("\U0001f7e2")

    def test_all_negative_prices_do_not_crash(self) -> None:
        # max_price <= 0: nothing to scale against, every bar floors to 1 cell.
        slots = _slots([-10.0, -5.0, -1.0])
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert all(row.count("▇") == 1 for row in rows)


class TestBilingual:
    def test_english_title_and_footer(self) -> None:
        text = render_price_bar_chart(_slots([5.3, 15.1]), _settings(language=Language.EN))
        assert "Today's prices" in text
        assert "Best wash time: from 00:00" in text

    def test_traditional_chinese_title_and_footer(self) -> None:
        text = render_price_bar_chart(_slots([5.3, 15.1]), _settings(language=Language.ZH))
        assert "今日電價走勢" in text
        assert "由 00:00 開始" in text

    def test_footer_recommends_cheapest_slot_time(self) -> None:
        # Cheapest is the second slot (00:30 BST), not the first in input order.
        slots = _slots([15.1, 5.3])
        text = render_price_bar_chart(slots, _settings())
        assert "00:30" in text.splitlines()[-2]

    def test_wrapped_in_markdown_code_block(self) -> None:
        text = render_price_bar_chart(_slots([5.3]), _settings())
        assert text.startswith("```\n")
        assert text.endswith("\n```")

    def test_default_title_is_today(self) -> None:
        text = render_price_bar_chart(_slots([5.3]), _settings())
        assert "Today's prices" in text

    def test_for_tomorrow_english_title(self) -> None:
        text = render_price_bar_chart(
            _slots([5.3]), _settings(language=Language.EN), for_tomorrow=True
        )
        assert "Tomorrow's prices" in text

    def test_for_tomorrow_traditional_chinese_title(self) -> None:
        text = render_price_bar_chart(
            _slots([5.3]), _settings(language=Language.ZH), for_tomorrow=True
        )
        assert "聽日電價走勢" in text


class TestSlotLimit:
    def test_default_limit_caps_shown_rows(self) -> None:
        slots = _slots([float(i) for i in range(1, 49)])  # 48 half-hour slots
        rows = _rows(render_price_bar_chart(slots, _settings()))
        assert len(rows) == 8  # ChatSettings default chart_slot_limit

    def test_custom_limit_is_respected(self) -> None:
        slots = _slots([float(i) for i in range(1, 49)])
        settings = _settings(chart_slot_limit=3)
        rows = _rows(render_price_bar_chart(slots, settings))
        assert len(rows) == 3

    def test_limit_keeps_the_cheapest_slots(self) -> None:
        slots = _slots([50.0, 40.0, 5.0, 10.0, 30.0])
        settings = _settings(chart_slot_limit=2)
        rows = _rows(render_price_bar_chart(slots, settings))
        prices = [float(row.split("p")[0].split()[-1]) for row in rows]
        assert prices == [5.0, 10.0]

    def test_fewer_slots_than_limit_shows_all(self) -> None:
        slots = _slots([5.0, 6.0])
        rows = _rows(render_price_bar_chart(slots, _settings(chart_slot_limit=48)))
        assert len(rows) == 2


class TestGuards:
    def test_empty_prices_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            render_price_bar_chart([], _settings())


class TestAvoidList:
    def test_avoid_list_present_for_expensive_slots(self) -> None:
        slots = _slots([float(i) for i in range(1, 21)])  # 20 half-hour slots
        text = render_price_bar_chart(slots, _settings())
        assert "Avoid heavy use" in text

    def test_avoid_list_default_count_matches_default_limit(self) -> None:
        slots = _slots([float(i) for i in range(1, 21)])  # no overlap with cheap section
        text = render_price_bar_chart(slots, _settings())
        assert len(_avoid_section(text)) == 8  # ChatSettings default chart_expensive_slot_limit

    def test_avoid_list_custom_limit_is_respected(self) -> None:
        slots = _slots([float(i) for i in range(1, 21)])
        settings = _settings(chart_expensive_slot_limit=3)
        text = render_price_bar_chart(slots, settings)
        assert len(_avoid_section(text)) == 3

    def test_avoid_list_is_most_expensive_first(self) -> None:
        slots = _slots([float(i) for i in range(1, 21)])
        text = render_price_bar_chart(slots, _settings())
        prices = [float(row.split("p")[0].split()[-1]) for row in _avoid_section(text)]
        assert prices == sorted(prices, reverse=True)

    def test_avoid_list_dedupes_slots_already_shown(self) -> None:
        # 10 slots, prices 1..10. Cheap section (default limit 8) shows 1-8.
        # The 8 most-expensive overall are 3-10; after dropping the ones
        # already shown (3-8), only 9 and 10 should remain.
        slots = _slots([float(i) for i in range(1, 11)])
        text = render_price_bar_chart(slots, _settings())
        avoid_prices = [float(row.split("p")[0].split()[-1]) for row in _avoid_section(text)]
        assert avoid_prices == [10.0, 9.0]

    def test_no_avoid_section_when_every_slot_already_shown(self) -> None:
        slots = _slots([5.0, 6.0])
        text = render_price_bar_chart(slots, _settings())
        assert _avoid_section(text) == []
        assert "Avoid heavy use" not in text

    def test_avoid_rows_use_the_row_helper_tier_and_bar(self) -> None:
        # Prices 23-30 exceed the default 20p red-tier threshold.
        slots = _slots([float(i) for i in range(1, 31)])
        text = render_price_bar_chart(slots, _settings())
        assert all(row.startswith("\U0001f534") for row in _avoid_section(text))  # 🔴, all pricey

    def test_message_is_truncated_rather_than_exceeding_the_length_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        slots = _slots([float(i) for i in range(1, 21)])
        settings = _settings(chart_expensive_slot_limit=8)
        full_text = render_price_bar_chart(slots, settings)

        # Cap the guard just below the untruncated length so a truncation is
        # forced, without depending on Telegram's real 4096-char limit.
        monkeypatch.setattr(renderer_module, "_TELEGRAM_MAX_MESSAGE_LENGTH", len(full_text) - 1)
        text = render_price_bar_chart(slots, settings)

        assert len(text) <= len(full_text) - 1
        assert "…" in text
        assert len(_avoid_section(text)) < 8
