from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class Skill(Document):
    name: str
    description: str = ""
    instructions: str  # The skill content injected into the system prompt
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "skills"
