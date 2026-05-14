import os as _os
from datetime import UTC, datetime
from typing import Literal

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


class ChatMessage(_DocumentBase):  # type: ignore[valid-type]
    """A single message within a chat session."""

    session_id: _IdType  # type: ignore[valid-type]
    role: Literal["user", "assistant"]
    content: str
    usage: dict | None = None  # token counts for assistant messages
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "chat_messages"
        indexes = [
            [("session_id", 1), ("created_at", 1)],
        ]
