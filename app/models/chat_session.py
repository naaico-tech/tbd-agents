from datetime import UTC, datetime

from beanie import Document, PydanticObjectId
from pydantic import Field


class ChatSession(Document):
    """A persistent multi-turn chat conversation between a user and an agent."""

    agent_id: PydanticObjectId
    github_user: str
    title: str | None = None  # auto-generated from first message
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_count: int = 0

    class Settings:
        name = "chat_sessions"
        indexes = [
            [("agent_id", 1), ("github_user", 1), ("updated_at", -1)],
        ]
