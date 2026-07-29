"""Unit tests for the price chart rendering service.

Pure presentation logic — no AWS, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from hrse.models.chat_settings import Language
from hrse.models.pricing import PricePoint
from hrse.services.price_chart import render_price_chart

_LONDON = ZoneInfo("Europe/London")
_UTC_MIDNIGHT = datetime(2026, 7, 11, 23, 0, tzinfo=UTC)  # 00:00 BST on 2026-07-12


def _day_of_points(prices: list[float]) -> list[PricePoint]:
    """Build consecutive half-hour PricePoints starting at local midnight."""
    return [
        PricePoint(timestamp=_UTC_MIDNIGHT + timedelta(minutes=30 * i), price_pence=p)
        for i, p in enumerate(prices)
    ]


def _bars_of(text: str) -> list[str]:
    """Extract the bar-chart lines from the <pre> block."""
    return text.split("<pre>")[1].split("</pre>")[0].strip().splitlines()


class TestBestWindowSummary:
    def test_summary_line_present_and_localised(self) -> None:
        points = _day_of_points([30.0, 5.0, 6.0, 7.0, 30.0])
        en = render_price_chart(points, Language.EN, _LONDON, window_slots=3)
        zh = render_price_chart(points, Language.ZH, _LONDON, window_slots=3)
        assert "Best 1.5h window" in en
        assert "最抵 1.5 小時窗口" in zh

    def test_summary_picks_cheapest_contiguous_run(self) -> None:
        # Cheapest 2-slot run is indices 3–4 (avg 5.0), not the single dip at 1.
        points = _day_of_points([30.0, 2.0, 30.0, 5.0, 5.0, 30.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        # Window starts at slot 3 == 01:30 BST, ends after slot 4 == 02:30 BST.
        assert "01:30\u201302:30" in text
        assert "avg <b>5.00p</b>" in text

    def test_window_shrinks_when_fewer_points_than_slots(self) -> None:
        points = _day_of_points([10.0, 12.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=4)
        assert len(_bars_of(text)) == 2  # only two slots available

    def test_hours_formats_whole_and_half(self) -> None:
        points = _day_of_points([10.0] * 6)
        assert "Best 2h window" in render_price_chart(points, Language.EN, _LONDON, window_slots=4)
        assert "Best 1.5h window" in render_price_chart(
            points, Language.EN, _LONDON, window_slots=3
        )


class TestBarChart:
    def test_one_bar_line_per_window_slot(self) -> None:
        points = _day_of_points([10.0, 5.0, 6.0, 7.0, 40.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=3)
        assert len(_bars_of(text)) == 3

    def test_bar_line_shows_label_and_price(self) -> None:
        points = _day_of_points([5.0, 6.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        first = _bars_of(text)[0]
        assert first.startswith("00:00")
        assert "5.00p" in first

    def test_full_price_bar_is_longer_than_cheap_bar(self) -> None:
        # Window covers both; dearer slot's bar should have more full blocks.
        points = _day_of_points([4.0, 40.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        rows = _bars_of(text)
        assert rows[1].count("\u2588") > rows[0].count("\u2588")

    def test_negative_price_shows_plunge_marker(self) -> None:
        points = _day_of_points([-3.0, 20.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        assert "\u25c0" in text  # plunge marker
        assert "-3.00p" in text

    def test_zero_max_produces_empty_bars_without_error(self) -> None:
        points = _day_of_points([0.0, 0.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        assert len(_bars_of(text)) == 2


class TestWholeDayStats:
    def test_stats_lines_present_and_localised(self) -> None:
        points = _day_of_points([10.0, 5.0, 30.0])
        en = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        zh = render_price_chart(points, Language.ZH, _LONDON, window_slots=2)
        assert "Cheapest" in en and "5.00p" in en
        assert "最平" in zh and "5.00p" in zh
        assert "Average" in en and "平均" in zh

    def test_stats_span_whole_day_not_just_window(self) -> None:
        # Most-expensive (40) sits outside the cheapest 2-slot window.
        points = _day_of_points([5.0, 6.0, 40.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=2)
        assert "40.00p" in text  # dearest still reported

    def test_cheapest_window_uses_display_timezone(self) -> None:
        # Cheapest slot starts 23:00 UTC == 00:00 BST.
        points = _day_of_points([5.0, 10.0])
        text = render_price_chart(points, Language.EN, _LONDON, window_slots=1)
        assert "00:00\u201300:30" in text


class TestGuards:
    def test_empty_points_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            render_price_chart([], Language.EN, _LONDON)

    def test_zero_window_slots_raises(self) -> None:
        points = _day_of_points([10.0])
        with pytest.raises(ValueError, match="window_slots"):
            render_price_chart(points, Language.EN, _LONDON, window_slots=0)
