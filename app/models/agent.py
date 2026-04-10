from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class Agent(Document):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None  # None → use workflow/global default
    mcp_server_ids: list[str] = Field(default_factory=list)
    tool_definitions: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "agents"
