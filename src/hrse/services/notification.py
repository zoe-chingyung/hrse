"""NotificationService — formats recommendations into Telegram messages.

Sprint 4 — Notification layer.

This service is pure: it has no AWS, network, or storage dependencies.
It takes a ``Recommendation`` and a ``NotificationKind`` and returns a
formatted HTML string ready to hand to ``TelegramClientProtocol.send_message``.

Two kinds of notification (matching the requirements doc):
* ``PLANNING``  — sent at 16:45, recommends a window for *tomorrow*.
* ``REMINDER``  — sent at 08:00, confirms (or withdraws) the recommendation
                  for *today* after overnight repricing.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from hrse.models.recommendation import Recommendation


class NotificationKind(str, Enum):
    """Which of the two daily notification messages to format."""

    PLANNING = "planning"
    REMINDER = "reminder"


class NotificationService:
    """Converts a ``Recommendation`` into a Telegram HTML message string.

    Args:
        display_tz: IANA timezone used to render window times and derive the
                    correct tz label (BST/GMT/etc.) for the instant in
                    question, so labels stay correct across the DST boundary.
    """

    def __init__(self, display_tz: ZoneInfo) -> None:
        self._display_tz = display_tz

    def format(self, rec: Recommendation, kind: NotificationKind) -> str:
        """Return a Telegram HTML string for the given recommendation.

        Args:
            rec:  The decision engine output.
            kind: Whether this is the 16:45 planning or 08:00 reminder message.

        Returns:
            A UTF-8 string with Telegram HTML formatting (bold, bullet points).
        """
        if kind == NotificationKind.PLANNING:
            return self._format_planning(rec)
        return self._format_reminder(rec)

    # ------------------------------------------------------------------
    # Private formatters
    # ------------------------------------------------------------------

    def _fmt_window(self, start: datetime, end: datetime) -> str:
        """Format a UTC window as 'HH:MM–HH:MM <label> (HH:MM–HH:MM UTC)'.

        The label (e.g. BST/GMT) is derived from ``tzname()`` at the window's
        start instant, so it is correct on both sides of the DST transition.
        """
        s_local = start.astimezone(self._display_tz)
        e_local = end.astimezone(self._display_tz)
        label = s_local.tzname()
        return f"{s_local:%H:%M}–{e_local:%H:%M} {label}" f"  ({start:%H:%M}–{end:%H:%M} UTC)"

    def _format_planning(self, rec: Recommendation) -> str:
        """16:45 message — tomorrow's energy plan."""
        lines = ["🏠 <b>Tomorrow's Energy Plan</b>"]

        if rec.recommended and rec.window is not None:
            lines.append("")
            lines.append("✅ <b>Laundry Recommended</b>")
            lines.append(f"🕐 Best window: {self._fmt_window(rec.window.start, rec.window.end)}")
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Estimated wash cost: {rec.expected_price_pence}p")
            lines.append("")
            lines.append("<b>Reasons:</b>")
            for r in rec.reasons:
                lines.append(f"  ✓ {r}")
        else:
            lines.append("")
            lines.append("❌ <b>Laundry not recommended tomorrow</b>")
            lines.append("")
            lines.append("<b>Reasons:</b>")
            for r in rec.reasons:
                lines.append(f"  • {r}")

        return "\n".join(lines)

    def _format_reminder(self, rec: Recommendation) -> str:
        """08:00 message — morning execution reminder."""
        lines = ["⏰ <b>Morning Reminder</b>"]

        if rec.recommended and rec.window is not None:
            lines.append("")
            lines.append("👕 Time to run laundry!")
            lines.append(f"🕐 Window: {self._fmt_window(rec.window.start, rec.window.end)}")
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Estimated wash cost: {rec.expected_price_pence}p")
            lines.append("")
            lines.append("Reply /laundry_done when finished.")
        else:
            lines.append("")
            lines.append("😴 No laundry needed today.")
            for r in rec.reasons:
                lines.append(f"  • {r}")

        return "\n".join(lines)
