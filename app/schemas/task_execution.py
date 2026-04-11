from datetime import datetime

from pydantic import BaseModel

from app.schemas.workflow import LogEntryResponse, MessageResponse, UsageStatsResponse


class TodoItemResponse(BaseModel):
    id: int
    title: str
    status: str  # "not-started" | "in-progress" | "completed"


class TaskProgressResponse(BaseModel):
    todos: list[TodoItemResponse] = []
    current_step: int | None = None
    percent_complete: float = 0.0


class TaskExecutionResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_title: str | None = None
    agent_name: str | None = None
    prompt: str
    status: str
    celery_task_id: str | None = None
    worker: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    tool_calls: int = 0
    response: str | None = None
    progress: TaskProgressResponse | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse] = []
    usage: UsageStatsResponse | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    created_at: datetime


class TaskExecutionSummary(BaseModel):
    """Lightweight version without logs/messages for list views."""
    id: str
    workflow_id: str
    workflow_title: str | None = None
    agent_name: str | None = None
    prompt: str
    status: str
    worker: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    tool_calls: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    elapsed_seconds: float | None = None
    created_at: datetime
