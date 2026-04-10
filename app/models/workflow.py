from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from beanie import Document
from pydantic import BaseModel, Field


class WorkflowStatus(StrEnum):
    ACTIVE = "active"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_TURNS_REACHED = "max_turns_reached"


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event: str  # e.g. "prompt_received", "model_call", "tool_call", "tool_result", "error", "completed"
    detail: str = ""


class Message(BaseModel):
    role: str  # system | user | assistant | tool
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class UsageStats(BaseModel):
    total_premium_requests: float = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0


class OutputDestination(BaseModel):
    notion_base_page_id: str | None = None
    slack_channel_id: str | None = None
    slack_user_id: str | None = None


class Workflow(Document):
    agent_id: str
    github_user: str
    model: str
    max_turns: int = 5
    current_turn: int = 0
    session_id: str | None = None  # Copilot SDK session ID
    skill_ids: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    logs: list[LogEntry] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    output_format: OutputFormat = OutputFormat.JSON
    usage: UsageStats | None = None
    output_destination: OutputDestination | None = None
    infinite_session: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "workflows"
