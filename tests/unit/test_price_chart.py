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


class TestRenderPriceChart:
    def test_empty_points_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            render_price_chart([], Language.EN, _LONDON)

    def test_full_day_renders_two_rows_of_24_blocks(self) -> None:
        points = _day_of_points([10.0 + i * 0.5 for i in range(48)])
        text = render_price_chart(points, Language.EN, _LONDON)
        pre = text.split("<pre>")[1].split("</pre>")[0].strip().splitlines()
        assert len(pre) == 2
        for row in pre:
            label, bars = row.split(" ", 1)
            assert len(bars) == 24
        assert pre[0].startswith("00:00")
        assert pre[1].startswith("12:00")

    def test_min_and_max_get_extreme_blocks(self) -> None:
        points = _day_of_points([20.0, 5.0, 35.0, 20.0])
        text = render_price_chart(points, Language.EN, _LONDON)
        bars = text.split("<pre>")[1].split("</pre>")[0].strip().split(" ", 1)[1]
        assert bars[1] == "▁"  # cheapest slot
        assert bars[2] == "█"  # most expensive slot

    def test_flat_prices_do_not_divide_by_zero(self) -> None:
        points = _day_of_points([15.0] * 4)
        text = render_price_chart(points, Language.EN, _LONDON)
        assert "▄" in text

    def test_negative_plunge_prices_render(self) -> None:
        points = _day_of_points([-2.0, 10.0, 30.0])
        text = render_price_chart(points, Language.EN, _LONDON)
        assert "-2.00p" in text

    def test_stats_lines_present_and_localised(self) -> None:
        points = _day_of_points([10.0, 5.0, 30.0])
        en = render_price_chart(points, Language.EN, _LONDON)
        zh = render_price_chart(points, Language.ZH, _LONDON)
        assert "Cheapest" in en and "5.00p" in en
        assert "最平" in zh and "5.00p" in zh
        assert "Average" in en
        assert "平均" in zh

    def test_window_times_use_display_timezone(self) -> None:
        # Cheapest slot starts 23:00 UTC == 00:00 BST.
        points = _day_of_points([5.0, 10.0])
        text = render_price_chart(points, Language.EN, _LONDON)
        assert "00:00–00:30" in text

    def test_partial_day_renders_short_row(self) -> None:
        points = _day_of_points([10.0, 12.0, 14.0])
        text = render_price_chart(points, Language.EN, _LONDON)
        bars = text.split("<pre>")[1].split("</pre>")[0].strip().split(" ", 1)[1]
        assert len(bars) == 3
