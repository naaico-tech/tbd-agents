from datetime import datetime

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None
    mcp_server_ids: list[str] = []
    mcp_server_tags: list[str] = []
    tool_definitions: list[dict] = []
    knowledge_source_ids: list[str] = []
    knowledge_tags: list[str] = []
    provider_id: str | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    mcp_server_ids: list[str] | None = None
    mcp_server_tags: list[str] | None = None
    tool_definitions: list[dict] | None = None
    knowledge_source_ids: list[str] | None = None
    knowledge_tags: list[str] | None = None
    provider_id: str | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    model: str | None
    mcp_server_ids: list[str]
    mcp_server_tags: list[str]
    tool_definitions: list[dict]
    knowledge_source_ids: list[str]
    knowledge_tags: list[str]
    provider_id: str | None
    created_at: datetime
    updated_at: datetime
