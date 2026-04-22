from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from beanie import Document
from pydantic import BaseModel, Field, field_validator


class WorkflowStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class OutputFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"


class LogEntry(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    event: str  # e.g. "prompt_received", "model_call", "tool_call", "tool_result", "error", "completed"
    detail: str = ""
    tool_input: str | None = None   # JSON-serialised tool arguments (for tool_call events)
    tool_output: str | None = None  # Tool result or error text (for tool_result events)


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
    title: str | None = None
    agent_id: str
    github_user: str
    model: str
    max_turns: int = 5
    current_turn: int = 0
    session_id: str | None = None  # Copilot SDK session ID
    skill_ids: list[str] = Field(default_factory=list)
    skill_tags: list[str] = Field(default_factory=list)  # Tag-based skill selection (union)
    messages: list[Message] = Field(default_factory=list)
    logs: list[LogEntry] = Field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.ACTIVE
    output_format: OutputFormat = OutputFormat.JSON

    @field_validator("status", mode="before")
    @classmethod
    def _normalise_legacy_status(cls, v: Any) -> str:
        """Map legacy execution statuses (completed, failed, etc.) to active."""
        if isinstance(v, str) and v not in (WorkflowStatus.ACTIVE, WorkflowStatus.INACTIVE):
            return WorkflowStatus.ACTIVE
        return v
    usage: UsageStats | None = None
    infinite_session: bool = True
    caveman: bool = False  # Enable terse caveman mode + context compression
    bypass_memory: bool = False  # Skip memory injection during task runs
    auto_memory: bool = False  # Auto-extract memories after task completion
    tsv_tool_results: bool = False  # Render tabular tool results as TSV before adding them to context
    reasoning_effort: str | None = None  # low | medium | high (model-dependent)
    guardrail_ids: list[str] = Field(default_factory=list)  # Explicitly selected guardrail IDs
    guardrail_tags: list[str] = Field(default_factory=list)  # Tag-based guardrail selection (union)
    repo_url: str | None = None  # GitHub repo URL to clone for agent access
    repo_branch: str | None = None  # Branch to checkout (default: main)
    repo_token_name: str | None = None  # Token Store key for private repo auth
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "workflows"
