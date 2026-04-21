from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UsageStatsResponse(BaseModel):
    total_premium_requests: float = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0


class WorkflowCreate(BaseModel):
    title: str | None = None
    agent_id: str
    max_turns: int | None = None
    output_format: str = "json"  # json | markdown
    model: str | None = None
    skill_ids: list[str] = []
    skill_tags: list[str] = []  # Tag-based skill selection (union)
    infinite_session: bool = True
    caveman: bool = False
    bypass_memory: bool = False  # Skip memory injection during task runs
    auto_memory: bool = False  # Auto-extract memories after task completion
    reasoning_effort: str | None = None  # low | medium | high
    guardrail_ids: list[str] = []  # Explicitly selected guardrail IDs
    guardrail_tags: list[str] = []  # Tag-based guardrail selection
    repo_url: str | None = None  # GitHub repo URL
    repo_branch: str | None = None  # Branch to checkout
    repo_token_name: str | None = None  # Token Store key for private repos


class WorkflowUpdate(BaseModel):
    title: str | None = None
    agent_id: str | None = None
    max_turns: int | None = None
    output_format: str | None = None
    model: str | None = None
    skill_ids: list[str] | None = None
    skill_tags: list[str] | None = None  # Tag-based skill selection (union)
    infinite_session: bool | None = None
    caveman: bool | None = None
    bypass_memory: bool | None = None
    auto_memory: bool | None = None
    reasoning_effort: str | None = None
    guardrail_ids: list[str] | None = None
    guardrail_tags: list[str] | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_token_name: str | None = None
    status: str | None = None  # active | inactive


class PromptRequest(BaseModel):
    prompt: str | None = None
    request: dict | None = None  # Structured request object for request-guardrail workflows
    reasoning_effort: str | None = None  # Override workflow default at prompt time


class MessageResponse(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LogEntryResponse(BaseModel):
    timestamp: datetime
    event: str
    detail: str


class PromptResponse(BaseModel):
    workflow_id: str
    status: str
    current_turn: int
    max_turns: int
    response: str | None = None
    output_format: str
    infinite_session: bool = True
    caveman: bool = False
    usage: UsageStatsResponse | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse] = []


class WorkflowResponse(BaseModel):
    id: str
    title: str | None = None
    agent_id: str
    github_user: str
    model: str
    max_turns: int
    current_turn: int
    session_id: str | None = None
    skill_ids: list[str]
    skill_tags: list[str] = []
    status: str
    output_format: str
    infinite_session: bool = True
    caveman: bool = False
    bypass_memory: bool = False
    auto_memory: bool = False
    reasoning_effort: str | None = None
    guardrail_ids: list[str] = []
    guardrail_tags: list[str] = []
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_token_name: str | None = None
    usage: UsageStatsResponse | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse]
    task_count: int = 0
    last_task_status: str | None = None
    last_task_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
