from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import Field


class ChatMessage(Document):
    """A single message within a chat session."""

    session_id: PydanticObjectId
    role: Literal["user", "assistant"]
    content: str
    usage: dict | None = None  # token counts for assistant messages
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "chat_messages"
        indexes = [
            [("session_id", 1), ("created_at", 1)],
        ]
