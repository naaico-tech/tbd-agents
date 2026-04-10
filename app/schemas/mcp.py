from datetime import datetime
from typing import Any

from pydantic import BaseModel


class McpServerCreate(BaseModel):
    name: str
    transport_type: str  # stdio | sse
    connection_config: dict[str, Any]
    allowed_tools: list[str] = []


class McpServerUpdate(BaseModel):
    name: str | None = None
    transport_type: str | None = None
    connection_config: dict[str, Any] | None = None
    allowed_tools: list[str] | None = None


class McpServerResponse(BaseModel):
    id: str
    name: str
    transport_type: str
    connection_config: dict[str, Any]
    allowed_tools: list[str] = []
    status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class McpTestResponse(BaseModel):
    success: bool
    tools: list[dict[str, Any]] = []
    error: str | None = None
