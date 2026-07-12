"""Price chart rendering — pure presentation service.

Renders a list of half-hourly ``PricePoint`` objects as a compact Telegram
message: a unicode bar chart (styled after the Octopus app's price histogram)
plus cheapest / most-expensive / average lines.

Design
------
* Pure Python — no AWS imports, no network. Fully unit-testable.
* One block character (▁▂▃▄▅▆▇█) per 30-minute slot, scaled linearly between
  the day's min and max price. Negative plunge prices scale correctly.
* Rows of 24 blocks (12 hours) keep the chart readable on a phone inside a
  ``<pre>`` block; each row is labelled with its local start time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from hrse.i18n import MessageKey, t

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import tzinfo

    from hrse.models.chat_settings import Language
    from hrse.models.pricing import PricePoint

_BLOCKS = "▁▂▃▄▅▆▇█"
_SLOTS_PER_ROW = 24  # 12 hours of half-hour slots per chart row
_SLOT_MINUTES = 30


def render_price_chart(
    points: Sequence[PricePoint],
    lang: Language,
    display_tz: tzinfo,
) -> str:
    """Render ``points`` as an HTML chart + stats message body.

    Args:
        points:     Half-hourly prices, assumed sorted oldest-first, non-empty.
        lang:       Display language for the stat labels.
        display_tz: Timezone used to format slot times.

    Returns:
        HTML-formatted message body (chart in ``<pre>``, stats below).

    Raises:
        ValueError: If ``points`` is empty.
    """
    if not points:
        raise ValueError("render_price_chart requires at least one PricePoint")

    prices = [p.price_pence for p in points]
    lo, hi = min(prices), max(prices)

    chart_rows = _chart_rows(points, lo, hi, display_tz)
    cheapest = min(points, key=lambda p: p.price_pence)
    dearest = max(points, key=lambda p: p.price_pence)
    average = sum(prices) / len(prices)

    return "\n".join(
        [
            "<pre>",
            *chart_rows,
            "</pre>",
            t(
                MessageKey.PRICES_CHEAPEST,
                lang,
                price=f"{cheapest.price_pence:.2f}",
                window=_window(cheapest, display_tz),
            ),
            t(
                MessageKey.PRICES_MOST_EXPENSIVE,
                lang,
                price=f"{dearest.price_pence:.2f}",
                window=_window(dearest, display_tz),
            ),
            t(MessageKey.PRICES_AVERAGE, lang, price=f"{average:.2f}"),
        ]
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _chart_rows(
    points: Sequence[PricePoint],
    lo: float,
    hi: float,
    display_tz: tzinfo,
) -> list[str]:
    """Build labelled rows of block characters, ``_SLOTS_PER_ROW`` per row."""
    rows: list[str] = []
    for start in range(0, len(points), _SLOTS_PER_ROW):
        chunk = points[start : start + _SLOTS_PER_ROW]
        label = chunk[0].timestamp.astimezone(display_tz).strftime("%H:%M")
        bars = "".join(_block(p.price_pence, lo, hi) for p in chunk)
        rows.append(f"{label} {bars}")
    return rows


def _block(price: float, lo: float, hi: float) -> str:
    """Map ``price`` onto one of the eight block characters."""
    if hi == lo:  # flat day — avoid division by zero
        return _BLOCKS[3]
    level = round((price - lo) / (hi - lo) * (len(_BLOCKS) - 1))
    return _BLOCKS[level]


def _window(point: PricePoint, display_tz: tzinfo) -> str:
    """Format a slot as ``HH:MM–HH:MM`` in the display timezone."""
    from datetime import timedelta

    start = point.timestamp.astimezone(display_tz)
    end = start + timedelta(minutes=_SLOT_MINUTES)
    return f"{start:%H:%M}–{end:%H:%M}"
