from datetime import datetime
from typing import Any

from pydantic import BaseModel


class McpServerCreate(BaseModel):
    name: str
    transport_type: str  # stdio | sse
    connection_config: dict[str, Any]


class McpServerResponse(BaseModel):
    id: str
    name: str
    transport_type: str
    connection_config: dict[str, Any]
    status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class McpTestResponse(BaseModel):
    success: bool
    tools: list[dict[str, Any]] = []
    error: str | None = None
