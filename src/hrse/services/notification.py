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
    from hrse.models.recommendation import Recommendation


class NotificationKind(str, Enum):
    """Which of the two daily notification messages to format."""

    PLANNING = "planning"
    REMINDER = "reminder"


class NotificationService:
    """Converts a ``Recommendation`` into a Telegram HTML message string."""

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

    @staticmethod
    def _format_planning(rec: Recommendation) -> str:
        """16:45 message — tomorrow's energy plan."""
        lines = ["🏠 <b>Tomorrow's Energy Plan</b>"]

        if rec.recommended and rec.window is not None:
            lines.append("")
            lines.append("✅ <b>Laundry Recommended</b>")
            lines.append(
                f"🕐 Best window: " f"{rec.window.start:%H:%M} – {rec.window.end:%H:%M} UTC"
            )
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Expected price: {rec.expected_price_pence}p/kWh")
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

    @staticmethod
    def _format_reminder(rec: Recommendation) -> str:
        """08:00 message — morning execution reminder."""
        lines = ["⏰ <b>Morning Reminder</b>"]

        if rec.recommended and rec.window is not None:
            lines.append("")
            lines.append("👕 Time to run laundry!")
            lines.append(f"🕐 Window: " f"{rec.window.start:%H:%M} – {rec.window.end:%H:%M} UTC")
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Price: {rec.expected_price_pence}p/kWh")
            lines.append("")
            lines.append("Reply /laundry_done when finished.")
        else:
            lines.append("")
            lines.append("😴 No laundry needed today.")
            for r in rec.reasons:
                lines.append(f"  • {r}")

        return "\n".join(lines)
