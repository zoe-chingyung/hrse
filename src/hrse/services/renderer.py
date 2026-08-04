"""Text/emoji price bar chart — pure presentation service.

Renders a list of half-hourly ``PriceSlot`` prices as a compact, monospace
bar chart for the daily Telegram notification: one row per slot, coloured by
a cheap/mid/expensive tier, plus a footer recommending the cheapest slot as
the wash time.

Design
------
* Pure Python — no AWS imports, no network. Fully unit-testable.
* Rows are sorted cheapest first so the best options are always at the top,
  which also matches the order used to pick the "best wash time" footer.
* Tier thresholds and the row-count limit are read from ``ChatSettings``
  (with sensible defaults), never hardcoded, so a chat can tune them via
  future settings commands without a code change.
* When there are more slots than the configured limit, only the cheapest
  ``chart_slot_limit`` are shown — that's the subset actually relevant to a
  "when should I run this" decision, and keeps the message short on a phone.
* The whole message is wrapped in a MarkdownV2 code block so Telegram
  renders it monospace and the bar/price columns stay aligned.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from hrse.i18n import MessageKey, t

if TYPE_CHECKING:
    from collections.abc import Sequence

    from hrse.models.chat_settings import ChatSettings
    from hrse.models.pricing import PriceSlot

_BAR_CHAR = "▇"  # ▇
_BAR_CELLS = 8
_GREEN = "\U0001f7e2"  # 🟢
_YELLOW = "\U0001f7e1"  # 🟡
_RED = "\U0001f534"  # 🔴
_CHECK = "✅"  # ✅
# Octopus Agile is UK-only, so this mirrors Settings.display_timezone's
# default — used only when a chat hasn't picked its own timezone.
_DEFAULT_DISPLAY_TZ = "Europe/London"


def render_price_bar_chart(prices: Sequence[PriceSlot], settings: ChatSettings) -> str:
    """Render ``prices`` as a bilingual, tiered bar chart for the daily notification.

    Args:
        prices:   Half-hourly prices, non-empty, in any order.
        settings: The chat's settings — supplies display language, timezone,
                  colour-tier thresholds and the row-count limit.

    Returns:
        A MarkdownV2 message: a triple-backtick code block containing the
        title, one row per shown slot, and a footer naming the cheapest slot
        as the recommended wash time.

    Raises:
        ValueError: If ``prices`` is empty.
    """
    if not prices:
        raise ValueError("render_price_bar_chart requires at least one PriceSlot")

    display_tz = ZoneInfo(settings.effective_timezone or _DEFAULT_DISPLAY_TZ)
    green = settings.chart_green_threshold_pence
    red = settings.chart_red_threshold_pence

    shown = sorted(prices, key=lambda slot: slot.price_pence)[: settings.chart_slot_limit]
    max_price = max(slot.price_pence for slot in shown)

    lang = settings.language
    cheapest_time = shown[0].timestamp.astimezone(display_tz).strftime("%H:%M")

    lines = [
        t(MessageKey.PRICE_BAR_CHART_TITLE, lang),
        "",
        *[_row(slot, display_tz, green, red, max_price) for slot in shown],
        "",
        t(MessageKey.PRICE_BAR_CHART_FOOTER, lang, time=cheapest_time),
    ]
    return "```\n" + "\n".join(lines) + "\n```"


def _tier(price: float, green: float, red: float) -> str:
    """Return the tier emoji for ``price`` against the ``green``/``red`` boundaries."""
    if price < green:
        return _GREEN
    if price <= red:
        return _YELLOW
    return _RED


def _row(slot: PriceSlot, display_tz: ZoneInfo, green: float, red: float, max_price: float) -> str:
    """Format one slot as ``<tier> HH:MM <price>p  <bar>``."""
    label = slot.timestamp.astimezone(display_tz).strftime("%H:%M")
    tier = _tier(slot.price_pence, green, red)
    bar = _BAR_CHAR * _bar_length(slot.price_pence, max_price)
    return f"{tier} {label}{slot.price_pence:>5.1f}p  {bar}"


def _bar_length(price: float, max_price: float) -> int:
    """Bar length in cells, baselined from 0 so negative prices floor at 1 cell.

    ``max_price`` may be non-positive (e.g. every shown slot is a plunge-price
    negative), in which case there's no positive scale to draw against and
    every bar is drawn at the 1-cell floor.
    """
    if max_price <= 0:
        return 1
    return max(1, round(price / max_price * _BAR_CELLS))
