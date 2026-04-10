from datetime import datetime

from pydantic import BaseModel


class AgentCreate(BaseModel):
    name: str
    description: str = ""
    system_prompt: str = "You are a helpful assistant."
    model: str | None = None
    mcp_server_ids: list[str] = []
    tool_definitions: list[dict] = []


class AgentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    model: str | None = None
    mcp_server_ids: list[str] | None = None
    tool_definitions: list[dict] | None = None


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    model: str | None
    mcp_server_ids: list[str]
    tool_definitions: list[dict]
    created_at: datetime
    updated_at: datetime
