import os as _os
from datetime import UTC, datetime
from enum import StrEnum

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


class TransportType(StrEnum):
    STDIO = "stdio"
    SSE = "sse"
    HTTP = "http"


class McpServerStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    ERROR = "error"


class McpServer(_DocumentBase):  # type: ignore[valid-type]
    name: str
    transport_type: TransportType
    connection_config: dict  # stdio: {command, args, env} | sse: {url, headers}
    allowed_tools: list[str] = Field(default_factory=list)  # empty = all tools
    tags: list[str] = Field(default_factory=list)
    status: McpServerStatus = McpServerStatus.REGISTERED
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "mcp_servers"
