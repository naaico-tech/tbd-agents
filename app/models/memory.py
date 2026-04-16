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
    metadata: dict = Field(default_factory=dict)
    ttl: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "memories"
