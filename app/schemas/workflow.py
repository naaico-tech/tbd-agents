from datetime import datetime
from typing import Any

from pydantic import BaseModel


class WorkflowCreate(BaseModel):
    agent_id: str
    max_turns: int | None = None
    output_format: str = "json"  # json | markdown
    model: str | None = None
    skill_ids: list[str] = []


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
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse] = []


class WorkflowResponse(BaseModel):
    id: str
    agent_id: str
    github_user: str
    model: str
    max_turns: int
    current_turn: int
    session_id: str | None = None
    skill_ids: list[str]
    status: str
    output_format: str
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse]
    created_at: datetime
    updated_at: datetime
