from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class Agent(Document):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None  # None → use workflow/global default
    mcp_server_ids: list[str] = Field(default_factory=list)
    mcp_server_tags: list[str] = Field(default_factory=list)
    tool_definitions: list[dict] = Field(default_factory=list)
    knowledge_source_ids: list[str] = Field(default_factory=list)
    knowledge_tags: list[str] = Field(default_factory=list)
    builtin_tools: list[str] = Field(default_factory=list)  # e.g. ["bash", "read", "write", "edit", "glob", "grep", "web_fetch", "web_search"]
    provider_id: str | None = None  # Optional BYOK provider reference
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "agents"
