from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import Field


class TransportType(StrEnum):
    STDIO = "stdio"
    SSE = "sse"


class McpServerStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    ERROR = "error"


class McpServer(Document):
    name: str
    transport_type: TransportType
    connection_config: dict  # stdio: {command, args, env} | sse: {url, headers}
    status: McpServerStatus = McpServerStatus.REGISTERED
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "mcp_servers"
