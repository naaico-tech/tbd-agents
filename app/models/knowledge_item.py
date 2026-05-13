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


class KnowledgeContentType(StrEnum):
    TEXT = "text"
    FILE = "file"
    IMAGE = "image"


class KnowledgeItem(_DocumentBase):  # type: ignore[valid-type]
    source_id: str
    name: str
    content_type: KnowledgeContentType
    text_content: str | None = None
    file_id: str | None = None  # GridFS file ID
    file_name: str | None = None
    file_size: int | None = None
    mime_type: str | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "knowledge_items"
