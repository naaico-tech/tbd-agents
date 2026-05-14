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


class MemoryScope(StrEnum):
    SESSION = "session"
    AGENT = "agent"
    GLOBAL = "global"


class Memory(_DocumentBase):  # type: ignore[valid-type]
    agent_id: str
    scope: MemoryScope
    key: str
    value: str
    embedding: list[float] | None = None
    metadata: dict = Field(default_factory=dict)
    ttl: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "memories"
