from datetime import datetime

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request body for sending a chat message."""

    message: str
    session_id: str | None = None  # omit to create a new session


class ChatMessageResponse(BaseModel):
    """A single persisted chat message."""

    id: str
    role: str  # "user" | "assistant"
    content: str
    usage: dict | None = None
    created_at: datetime


class ChatSessionResponse(BaseModel):
    """Summary view of a chat session (no messages)."""

    id: str
    agent_id: str
    title: str | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(ChatSessionResponse):
    """Full session view including message history."""

    messages: list[ChatMessageResponse] = []
