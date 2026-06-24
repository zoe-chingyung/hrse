"""DecisionService — the laundry recommendation engine.

This service is pure: it has no AWS, network, or storage dependencies. It
takes already-fetched inputs (weekly summary, prices, forecast, config) and
returns a ``Recommendation``. That makes it fully testable with plain
constructed objects, mirroring ``WeeklyStateService``.

The five rules (Section 10 of the requirements)
-----------------------------------------------
1. Target check  — if the weekly target is already met, do not recommend.
2. Valid windows — build candidate runs of ``duration_slots`` consecutive
                   30-minute slots that fall entirely inside the configured
                   ``earliest_start``..``latest_finish`` window.
3. Price filter  — keep only candidates where the average slot price satisfies
                   ``avg_price * machine_kwh < wash_budget_pence``.
4. Weather filter — gate on the day's forecast: UV strictly above ``min_uv``
                   and rain probability strictly below ``max_rain_probability``.
5. Rank          — choose the cheapest candidate (lowest total cost), breaking
                   ties by earliest start.

Window cost
-----------
A candidate's cost is the sum of its slot prices. ``expected_price_pence`` on
the recommendation reports the average price per slot, which is the more
intuitive "p/kWh" figure for the user-facing message.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from aws_lambda_powertools import Logger

from hrse.models.recommendation import Recommendation, RecommendationWindow

if TYPE_CHECKING:
    from hrse.models.events import WeeklySummary
    from hrse.models.pricing import PricePoint
    from hrse.models.task_config import LaundryTaskConfig
    from hrse.models.weather import DailyForecast

logger = Logger(child=True)

_SLOT = timedelta(minutes=30)
_TASK = "laundry"


class _Candidate:
    """An internal candidate run: a contiguous block of priced slots."""

    __slots__ = ("slots",)

    def __init__(self, slots: list[PricePoint]) -> None:
        self.slots = slots

    @property
    def total_cost(self) -> float:
        return sum(s.price_pence for s in self.slots)

    @property
    def avg_cost(self) -> float:
        return self.total_cost / len(self.slots)


class DecisionService:
    """Evaluates the five rules and produces a laundry ``Recommendation``."""

    def evaluate(
        self,
        summary: WeeklySummary,
        prices: list[PricePoint],
        forecast: DailyForecast,
        config: LaundryTaskConfig,
    ) -> Recommendation:
        """Run the rules and return a recommendation.

        Args:
            summary:  Weekly activity summary (drives Rule 1).
            prices:   Half-hourly prices for the candidate day, any order.
            forecast: The day's weather summary (drives Rule 4).
            config:   The user's laundry constraints.

        Returns:
            A ``Recommendation``; ``recommended`` is False with an explanatory
            reason whenever no acceptable window exists.
        """
        # Rule 1 — target already met?
        if summary.laundry_count >= config.target_runs_per_week:
            logger.debug("Laundry target already met", extra={"count": summary.laundry_count})
            return Recommendation(
                task=_TASK, recommended=False, reasons=["laundry target already met"]
            )

        # Rule 4 (day-level gate) — apply weather before bothering with slots.
        weather_reasons = self._weather_failures(forecast, config)
        if weather_reasons:
            return Recommendation(task=_TASK, recommended=False, reasons=weather_reasons)

        # Rule 2 — build valid contiguous candidate windows within the time range.
        candidates = self._candidate_windows(prices, config)
        if not candidates:
            return Recommendation(
                task=_TASK,
                recommended=False,
                reasons=["no valid execution window in the allowed time range"],
            )

        # Rule 3 — keep windows where avg price * machine_kwh < wash_budget_pence.
        # This compares total wash cost against the user's budget rather than
        # gating on individual slot prices, which is more realistic.
        price_threshold = config.wash_budget_pence / config.machine_kwh
        affordable = [c for c in candidates if c.avg_cost < price_threshold]
        if not affordable:
            est_cost = round(min(c.avg_cost for c in candidates) * config.machine_kwh, 1)
            return Recommendation(
                task=_TASK,
                recommended=False,
                reasons=[
                    f"cheapest window would cost ~{est_cost}p"
                    f" vs budget of {config.wash_budget_pence}p"
                ],
            )

        # Rule 5 — rank: cheapest total cost, then earliest start.
        best = min(affordable, key=lambda c: (c.total_cost, c.slots[0].timestamp))

        window = RecommendationWindow(
            start=best.slots[0].timestamp,
            end=best.slots[-1].timestamp + _SLOT,
        )
        reasons = [
            "laundry target not met",
            f"wash cost within budget ({config.wash_budget_pence}p)",
            f"UV index above {config.min_uv}",
            f"rain probability below {config.max_rain_probability}%",
        ]
        logger.info(
            "Laundry recommended",
            extra={"start": window.start.isoformat(), "avg_pence": round(best.avg_cost, 2)},
        )
        return Recommendation(
            task=_TASK,
            recommended=True,
            window=window,
            expected_price_pence=round(best.avg_cost * config.machine_kwh, 1),
            reasons=reasons,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _weather_failures(forecast: DailyForecast, config: LaundryTaskConfig) -> list[str]:
        """Return reasons the weather fails the gate, or an empty list if it passes."""
        reasons: list[str] = []
        if forecast.uv_index <= config.min_uv:
            reasons.append(f"UV index too low ({forecast.uv_index} <= {config.min_uv})")
        if forecast.rain_probability >= config.max_rain_probability:
            reasons.append(
                f"rain probability too high "
                f"({forecast.rain_probability}% >= {config.max_rain_probability}%)"
            )
        return reasons

    @staticmethod
    def _candidate_windows(prices: list[PricePoint], config: LaundryTaskConfig) -> list[_Candidate]:
        """Build all contiguous candidate windows inside the allowed time range.

        A candidate is ``duration_slots`` consecutive 30-minute slots where:
          * every slot starts at or after ``earliest_start`` (local clock time),
          * the final slot ends at or before ``latest_finish``,
          * slots are genuinely back-to-back (exactly 30 minutes apart).

        Args:
            prices: Half-hourly prices (any order).
            config: User constraints.

        Returns:
            A list of ``_Candidate`` windows; empty if none fit.
        """
        ordered = sorted(prices, key=lambda p: p.timestamp)
        n = config.duration_slots
        earliest = config.earliest_start_time
        latest = config.latest_finish_time

        candidates: list[_Candidate] = []
        for i in range(len(ordered) - n + 1):
            block = ordered[i : i + n]

            # Contiguity: each slot exactly 30 minutes after the previous.
            if any(
                block[j + 1].timestamp - block[j].timestamp != _SLOT for j in range(len(block) - 1)
            ):
                continue

            start_time = block[0].timestamp.time()
            end_time = (block[-1].timestamp + _SLOT).time()

            if start_time < earliest or end_time > latest:
                continue

            candidates.append(_Candidate(block))

        return candidates
