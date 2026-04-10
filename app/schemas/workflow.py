from datetime import datetime
from typing import Any

from pydantic import BaseModel


class OutputDestinationCreate(BaseModel):
    notion_base_page_id: str | None = None
    slack_channel_id: str | None = None
    slack_user_id: str | None = None


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
    infinite_session: bool = True
    output_destination: OutputDestinationCreate | None = None


class WorkflowUpdate(BaseModel):
    title: str | None = None
    max_turns: int | None = None
    output_format: str | None = None
    model: str | None = None
    skill_ids: list[str] | None = None
    infinite_session: bool | None = None
    output_destination: OutputDestinationCreate | None = None


class PromptRequest(BaseModel):
    prompt: str


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
    usage: UsageStatsResponse | None = None
    output_destination: OutputDestinationCreate | None = None
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
    status: str
    output_format: str
    infinite_session: bool = True
    usage: UsageStatsResponse | None = None
    output_destination: OutputDestinationCreate | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
