"""Core domain models for schedules and resources.

These are intentionally minimal stubs. Business logic will be added in
Sprint 2 once the data contracts are finalised.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class ScheduleStatus(StrEnum):
    """Lifecycle states of a schedule."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ResourceType(StrEnum):
    """Categories of household resources."""

    APPLIANCE = "APPLIANCE"
    ENERGY_SLOT = "ENERGY_SLOT"
    PERSON = "PERSON"


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


class TimeWindow(BaseModel):
    """A half-open time interval [start, end)."""

    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def end_must_be_after_start(cls, v: datetime, info: object) -> datetime:  # noqa: N805
        # info.data may not have 'start' yet if validation failed before this field
        data = getattr(info, "data", {})
        start = data.get("start")
        if start is not None and v <= start:
            raise ValueError("end must be strictly after start")
        return v


class Resource(BaseModel):
    """A named household resource."""

    id: Annotated[str, Field(default_factory=lambda: str(uuid.uuid4()))]
    name: str = Field(..., min_length=1, max_length=128)
    resource_type: ResourceType
    metadata: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregate root
# ---------------------------------------------------------------------------


class Schedule(BaseModel):
    """Root aggregate representing a single scheduling record."""

    id: Annotated[str, Field(default_factory=lambda: str(uuid.uuid4()))]
    household_id: str = Field(..., min_length=1)
    status: ScheduleStatus = ScheduleStatus.PENDING
    window: TimeWindow
    resources: list[Resource] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        # Allow mutation so services can update fields without rebuilding the model
        frozen = False
