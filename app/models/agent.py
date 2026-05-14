import os as _os
from datetime import UTC, datetime

from pydantic import Field

_POSTGRES = _os.environ.get("DB_BACKEND", "mongo").lower() == "postgres"

if _POSTGRES:
    from pydantic import BaseModel as _PyBase
    from pydantic import Field as _PgField

    from app.db_postgres import PostgresDocument as _PgBase

    class _DocumentBase(_PgBase, _PyBase):  # type: ignore[misc]
        id: str | None = _PgField(default=None)

else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]


class Agent(_DocumentBase):  # type: ignore[valid-type]
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
    custom_tool_ids: list[str] = Field(default_factory=list)  # IDs of CustomTool documents to mount on this agent
    provider_id: str | None = None  # Optional BYOK provider reference
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "agents"
