"""Price chart rendering — pure presentation service.

Renders a list of half-hourly ``PricePoint`` objects as a compact Telegram
message: a summary of the cheapest contiguous run-length window, a horizontal
bar chart of that window (one slot per line), and cheapest / most-expensive /
average lines computed across the whole day.

Design
------
* Pure Python — no AWS imports, no network. Fully unit-testable.
* Horizontal bars: one line per 30-minute slot, ``HH:MM │ ████▊ 12.34p``.
  Bar length scales linearly from the **day's minimum** price to its maximum,
  using fractional block characters (``█▉▊▋▌``) for sub-cell precision, so the
  cheapest slot is empty and the dearest is full — comparable across windows.
* Negative (plunge) prices are prefixed with a ``◀`` marker so they stand out
  as "cheaper than free", independent of bar length.
* Only the cheapest contiguous ``window_slots`` window is drawn as bars,
  keeping the message short on a phone; whole-day stats still appear below.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from hrse.i18n import MessageKey, t

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import tzinfo

    from hrse.models.chat_settings import Language
    from hrse.models.pricing import PricePoint

# Eighths of a full block, index 0..8. Index 0 is a single space (empty bar);
# 1..8 are the partial-to-full block glyphs. Reversed relative to the usual
# left-growing set so that ``_BAR_EIGHTHS[8] == "█"`` (full cell).
_BAR_EIGHTHS = " ▏▎▍▌▋▊▉█"
_MAX_BAR_CELLS = 10  # widest a full-price bar can get, in whole cells
_PLUNGE_MARKER = "◀"
_SLOT_MINUTES = 30


def render_price_chart(
    points: Sequence[PricePoint],
    lang: Language,
    display_tz: tzinfo,
    window_slots: int = 4,
) -> str:
    """Render ``points`` as an HTML summary + horizontal bar chart.

    Args:
        points:       Half-hourly prices, assumed sorted oldest-first, non-empty.
        lang:         Display language for the stat labels.
        display_tz:   Timezone used to format slot times.
        window_slots: Length of the contiguous "best window" to highlight, as a
                      count of 30-minute slots (4 = 2 hours). Clamped to the
                      number of available points.

    Returns:
        HTML-formatted message body (best-window line, chart in ``<pre>``,
        whole-day stats below).

    Raises:
        ValueError: If ``points`` is empty or ``window_slots`` < 1.
    """
    if not points:
        raise ValueError("render_price_chart requires at least one PricePoint")
    if window_slots < 1:
        raise ValueError("window_slots must be >= 1")

    prices = [p.price_pence for p in points]
    lo, hi = min(prices), max(prices)

    win_start, win_len, win_avg = _best_window(points, window_slots)
    window = points[win_start : win_start + win_len]

    bar_rows = [_bar_row(p, lo, hi, display_tz) for p in window]

    cheapest = min(points, key=lambda p: p.price_pence)
    dearest = max(points, key=lambda p: p.price_pence)
    average = sum(prices) / len(prices)

    return "\n".join(
        [
            t(
                MessageKey.PRICES_BEST_WINDOW,
                lang,
                hours=_fmt_hours(win_len),
                window=_window_span(window, display_tz),
                price=f"{win_avg:.2f}",
            ),
            "<pre>",
            *bar_rows,
            "</pre>",
            t(
                MessageKey.PRICES_CHEAPEST,
                lang,
                price=f"{cheapest.price_pence:.2f}",
                window=_slot_window(cheapest, display_tz),
            ),
            t(
                MessageKey.PRICES_MOST_EXPENSIVE,
                lang,
                price=f"{dearest.price_pence:.2f}",
                window=_slot_window(dearest, display_tz),
            ),
            t(MessageKey.PRICES_AVERAGE, lang, price=f"{average:.2f}"),
        ]
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _best_window(
    points: Sequence[PricePoint],
    window_slots: int,
) -> tuple[int, int, float]:
    """Find the cheapest contiguous window of up to ``window_slots`` slots.

    Uses a simple sliding sum. When fewer points than ``window_slots`` exist,
    the window shrinks to all available points.

    Args:
        points:       Half-hourly prices, oldest-first, non-empty.
        window_slots: Desired window length in slots.

    Returns:
        A tuple ``(start_index, length, average_price)`` for the cheapest
        contiguous window.
    """
    length = min(window_slots, len(points))
    prices = [p.price_pence for p in points]

    best_start = 0
    running = sum(prices[:length])
    best_sum = running
    for start in range(1, len(points) - length + 1):
        running += prices[start + length - 1] - prices[start - 1]
        if running < best_sum:
            best_sum = running
            best_start = start

    return best_start, length, best_sum / length


def _bar_row(point: PricePoint, lo: float, hi: float, display_tz: tzinfo) -> str:
    """Format one slot as ``HH:MM │ <bar> <price>p``.

    The bar scales linearly from the day's minimum (``lo``, zero-length) to its
    maximum (``hi``, full-length). Negative plunge prices are additionally
    flagged with a leading marker so they read as "cheaper than free".
    """
    label = point.timestamp.astimezone(display_tz).strftime("%H:%M")
    bar = _bar(point.price_pence, lo, hi)
    marker = f"{_PLUNGE_MARKER} " if point.price_pence < 0 else ""
    return f"{label} \u2502 {marker}{bar} {point.price_pence:.2f}p"


def _bar(price: float, lo: float, hi: float) -> str:
    """Build a fractional block bar for ``price`` scaled from ``lo`` to ``hi``.

    Args:
        price: The slot price in pence.
        lo:    The day's minimum price (bar zero-length point).
        hi:    The day's maximum price (bar full-scale point).

    Returns:
        A string of block characters. A flat day (``hi == lo``) yields an empty
        (space) bar for every slot.
    """
    if hi <= lo:  # flat day — no range to scale against
        return _BAR_EIGHTHS[0]

    fraction = (price - lo) / (hi - lo)
    eighths = round(fraction * _MAX_BAR_CELLS * 8)
    full, rem = divmod(eighths, 8)
    bar = "\u2588" * full
    if rem:
        bar += _BAR_EIGHTHS[rem]
    return bar or _BAR_EIGHTHS[0]


def _fmt_hours(slots: int) -> str:
    """Render a slot count as a compact hour string ('2' or '1.5')."""
    hours = slots * _SLOT_MINUTES / 60
    return f"{hours:g}"


def _slot_window(point: PricePoint, display_tz: tzinfo) -> str:
    """Format a single slot as ``HH:MM–HH:MM`` in the display timezone."""
    start = point.timestamp.astimezone(display_tz)
    end = start + timedelta(minutes=_SLOT_MINUTES)
    return f"{start:%H:%M}\u2013{end:%H:%M}"


def _window_span(window: Sequence[PricePoint], display_tz: tzinfo) -> str:
    """Format a multi-slot window as ``HH:MM–HH:MM`` in the display timezone."""
    start = window[0].timestamp.astimezone(display_tz)
    end = window[-1].timestamp.astimezone(display_tz) + timedelta(minutes=_SLOT_MINUTES)
    return f"{start:%H:%M}\u2013{end:%H:%M}"
