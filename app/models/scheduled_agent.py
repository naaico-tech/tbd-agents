"""Beanie/PostgreSQL document model for a Scheduled Agent trigger."""

import os as _os
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

_POSTGRES = _os.environ.get("DB_BACKEND", "mongo").lower() == "postgres"

if _POSTGRES:
    from pydantic import BaseModel as _PyBase
    from pydantic import Field as _PgField

    from app.db_postgres import PostgresDocument as _PgBase

    class _DocumentBase(_PgBase, _PyBase):  # type: ignore[misc]
        id: str | None = _PgField(default=None)

else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]


class ScheduleInterval(StrEnum):
    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class ScheduledAgent(_DocumentBase):  # type: ignore[valid-type]
    """A recurring schedule that fires a workflow at a configurable cadence.

    Each tick dispatches a ``run_agent_task`` Celery task exactly as if a user
    had submitted the prompt manually, producing a ``TaskExecution`` record.
    """

    name: str
    workflow_id: str                         # Which Workflow document to run
    prompt: str                              # Prompt injected on every tick
    interval_value: int = Field(ge=1)        # e.g. 30
    interval_unit: ScheduleInterval          # minutes | hours | days

    # Timing
    start_at: datetime                       # First run (UTC). Beat fires from here.
    end_at: datetime | None = None           # Optional hard stop (UTC). None = forever.

    # State
    enabled: bool = True
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None

    # RedBeat stores a unique key per schedule entry; we persist it so we can
    # delete / update the Beat entry without scanning Redis.
    redbeat_key: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "scheduled_agents"
