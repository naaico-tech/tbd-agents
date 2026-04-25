"""Pydantic request/response schemas for Scheduled Agent endpoints."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.scheduled_agent import ScheduleInterval


class ScheduledAgentCreate(BaseModel):
    name: str
    workflow_id: str
    prompt: str
    interval_value: int = Field(ge=1, description="Repeat every N units (≥ 1)")
    interval_unit: ScheduleInterval = ScheduleInterval.HOURS
    start_at: datetime
    end_at: datetime | None = None


class ScheduledAgentUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    interval_value: int | None = Field(default=None, ge=1)
    interval_unit: ScheduleInterval | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None


class ScheduledAgentResponse(BaseModel):
    id: str
    name: str
    workflow_id: str
    prompt: str
    interval_value: int
    interval_unit: ScheduleInterval
    start_at: datetime
    end_at: datetime | None
    enabled: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
