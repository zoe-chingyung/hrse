"""Domain models for electricity pricing.

Sprint 3 — Decision inputs.

Octopus Agile publishes prices in 30-minute settlement periods. Each
``PricePoint`` represents one such period: the price applies from
``timestamp`` for the following 30 minutes.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TCH003 — used as Pydantic field type at runtime

from pydantic import BaseModel, ConfigDict, Field


class PricePoint(BaseModel):
    """A single 30-minute electricity price.

    Attributes:
        timestamp:   UTC start of the 30-minute settlement period.
        price_pence: Price in pence per kWh for that period. May be negative
                     during Agile plunge-pricing events, so no lower bound.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(..., description="UTC start of the 30-minute period")
    price_pence: float = Field(..., description="Price in pence/kWh for this period")
