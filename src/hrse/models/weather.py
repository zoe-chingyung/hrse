"""Domain models for weather forecasts.

Sprint 3 — Decision inputs.

The MVP only needs a single daily summary forecast (not hourly), matching
the requirements doc: max temperature, UV index, and rain probability.
"""

from __future__ import annotations

from datetime import date  # noqa: TCH003 — used as Pydantic field type at runtime

from pydantic import BaseModel, ConfigDict, Field


class DailyForecast(BaseModel):
    """A one-day weather summary used by the decision engine.

    Attributes:
        forecast_date:     The calendar date this forecast applies to.
        temperature_max:   Maximum air temperature for the day, in degrees C.
        uv_index:          Peak UV index for the day (0-11+ scale).
        rain_probability:  Chance of precipitation for the day, as a percentage
                           in the range 0-100.
    """

    model_config = ConfigDict(frozen=True)

    forecast_date: date = Field(..., description="Date the forecast applies to")
    temperature_max: float = Field(..., description="Max temperature in degrees Celsius")
    uv_index: float = Field(..., ge=0, description="Peak UV index for the day")
    rain_probability: int = Field(
        ..., ge=0, le=100, description="Chance of rain as a percentage (0-100)"
    )
