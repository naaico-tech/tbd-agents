from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import BaseModel, Field

from app.models.workflow import LogEntry, Message, UsageStats


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"
    MAX_TURNS_REACHED = "max_turns_reached"


class TodoItemStatus(StrEnum):
    NOT_STARTED = "not-started"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"


class TodoItem(BaseModel):
    id: int
    title: str
    status: TodoItemStatus = TodoItemStatus.NOT_STARTED


class TaskProgress(BaseModel):
    todos: list[TodoItem] = Field(default_factory=list)
    current_step: int | None = None  # id of the in-progress item
    percent_complete: float = 0.0  # 0.0 – 1.0


class TaskExecution(Document):
    workflow_id: str
    prompt: str
    status: TaskStatus = TaskStatus.PENDING
    celery_task_id: str | None = None
    worker: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    tool_calls: int = 0
    response: str | None = None
    progress: TaskProgress | None = None
    logs: list[LogEntry] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    usage: UsageStats | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    scheduled_agent_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "task_executions"
