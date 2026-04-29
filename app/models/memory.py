from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import Field


class MemoryScope(StrEnum):
    SESSION = "session"
    AGENT = "agent"
    GLOBAL = "global"


class Memory(Document):
    agent_id: str
    scope: MemoryScope
    key: str
    value: str
    embedding: list[float] | None = None
    importance_score: float = Field(default=0.5)
    metadata: dict = Field(default_factory=dict)
    ttl: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "memories"
        indexes = [
            [("agent_id", 1), ("scope", 1), ("key", 1)],
            [("agent_id", 1), ("importance_score", -1)],
        ]
