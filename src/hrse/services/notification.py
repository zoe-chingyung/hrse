"""NotificationService — formats recommendations into Telegram messages.

Sprint 4  — Notification layer.
Sprint 5C — Multi-task messages (one block per enabled task).

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
    from collections.abc import Sequence
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from hrse.models.recommendation import Recommendation


class NotificationKind(str, Enum):
    """Which of the two daily notification messages to format."""

    PLANNING = "planning"
    REMINDER = "reminder"


# Display label per task registry key / Recommendation.task value. Falls
# back to a title-cased version of the raw task string for anything unlisted.
_TASK_LABELS: dict[str, str] = {
    "laundry": "🧺 Laundry",
    "dishwasher": "🍽 Dishwasher",
    "ev_charging": "🔌 EV Charging",
}


def _task_label(task: str) -> str:
    """Return a display label for ``task``, falling back to a generic one."""
    return _TASK_LABELS.get(task, task.replace("_", " ").title())


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

    def format_multi(
        self, recommendations: Sequence[Recommendation], kind: NotificationKind
    ) -> str:
        """Format one message covering every enabled task's recommendation.

        With exactly one recommendation this delegates to ``format()``, so a
        chat with only "laundry" enabled (the pre-5C default) gets a
        byte-identical message to before multi-task support existed. With
        more than one, renders a single header followed by one block per
        task, in the order given.

        Args:
            recommendations: One ``Recommendation`` per enabled task, non-empty.
            kind:             Whether this is the planning or reminder message.

        Returns:
            A UTF-8 string with Telegram HTML formatting.

        Raises:
            ValueError: If ``recommendations`` is empty.
        """
        if not recommendations:
            raise ValueError("format_multi requires at least one Recommendation")
        if len(recommendations) == 1:
            return self.format(recommendations[0], kind)

        header = (
            "🏠 <b>Tomorrow's Energy Plan</b>"
            if kind == NotificationKind.PLANNING
            else "⏰ <b>Morning Reminder</b>"
        )
        block_fn = (
            self._task_block_planning
            if kind == NotificationKind.PLANNING
            else self._task_block_reminder
        )
        blocks = [block_fn(rec) for rec in recommendations]
        return "\n\n".join([header, *blocks])

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

    def _task_block_planning(self, rec: Recommendation) -> str:
        """One task's block within a multi-task planning message."""
        lines = [f"<b>{_task_label(rec.task)}</b>"]
        if rec.recommended and rec.window is not None:
            lines.append("✅ Recommended")
            lines.append(f"🕐 Best window: {self._fmt_window(rec.window.start, rec.window.end)}")
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Estimated cost: {rec.expected_price_pence}p")
            for r in rec.reasons:
                lines.append(f"  ✓ {r}")
        else:
            lines.append("❌ Not recommended")
            for r in rec.reasons:
                lines.append(f"  • {r}")
        return "\n".join(lines)

    def _task_block_reminder(self, rec: Recommendation) -> str:
        """One task's block within a multi-task reminder message."""
        lines = [f"<b>{_task_label(rec.task)}</b>"]
        if rec.recommended and rec.window is not None:
            lines.append(f"🕐 Window: {self._fmt_window(rec.window.start, rec.window.end)}")
            if rec.expected_price_pence is not None:
                lines.append(f"⚡ Estimated cost: {rec.expected_price_pence}p")
            if rec.task == "laundry":
                lines.append("Reply /laundry_done when finished.")
        else:
            lines.append("😴 Not needed today.")
            for r in rec.reasons:
                lines.append(f"  • {r}")
        return "\n".join(lines)
