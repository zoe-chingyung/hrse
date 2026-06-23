"""Decision engine output models.

Sprint 3 — Recommendation object.

Mirrors Section 11 of the requirements. Deliberately self-contained: it
defines its own ``RecommendationWindow`` so the decision path stays
self-contained.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — used as Pydantic field type at runtime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RecommendationWindow(BaseModel):
    """A concrete recommended execution window [start, end)."""

    model_config = ConfigDict(frozen=True)

    start: datetime = Field(..., description="UTC start of the recommended window")
    end: datetime = Field(..., description="UTC end of the recommended window")

    @model_validator(mode="after")
    def _end_after_start(self) -> RecommendationWindow:
        """Ensure the window is non-empty."""
        if self.end <= self.start:
            raise ValueError("end must be strictly after start")
        return self


class Recommendation(BaseModel):
    """The decision engine's verdict for a single task.

    Attributes:
        task:        The task identifier, e.g. "laundry".
        recommended: Whether the engine recommends running the task.
        window:      The chosen execution window, or None when not recommended.
        expected_price_pence: Price of the chosen slot, or None when not recommended.
        reasons:     Human-readable explanations behind the verdict.
    """

    model_config = ConfigDict(frozen=True)

    task: str = Field(..., min_length=1, description="Task identifier")
    recommended: bool = Field(..., description="Whether the task is recommended")
    window: RecommendationWindow | None = Field(
        default=None, description="Chosen execution window, if recommended"
    )
    expected_price_pence: float | None = Field(
        default=None, description="Price of the chosen slot in pence/kWh"
    )
    reasons: list[str] = Field(default_factory=list, description="Explanations for the verdict")
