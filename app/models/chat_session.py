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

    _IdType = str
else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]
    from beanie import PydanticObjectId

    _IdType = PydanticObjectId  # type: ignore[assignment,misc]


class ChatSession(_DocumentBase):  # type: ignore[valid-type]
    """A persistent multi-turn chat conversation between a user and an agent."""

    agent_id: _IdType  # type: ignore[valid-type]
    github_user: str
    title: str | None = None  # auto-generated from first message
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    message_count: int = 0

    class Settings:
        name = "chat_sessions"
        indexes = [
            [("agent_id", 1), ("github_user", 1), ("updated_at", -1)],
        ]
