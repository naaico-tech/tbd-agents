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


class KnowledgeSourceType(StrEnum):
    VECTOR_DB = "vector_db"
    MONGO_DB = "mongo_db"
    PGVECTOR = "pgvector"


class KnowledgeSourceStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    ERROR = "error"


class KnowledgeSource(_DocumentBase):  # type: ignore[valid-type]
    name: str
    description: str = ""
    source_type: KnowledgeSourceType
    connection_config: dict = Field(
        default_factory=dict,
        # vector_db:  {url, collection, api_key_token_name}
        # pgvector:   {dsn, collection, dsn_token_name}
        #               dsn_token_name is optional; when set it overrides `dsn`
    )
    tags: list[str] = Field(default_factory=list)
    status: KnowledgeSourceStatus = KnowledgeSourceStatus.REGISTERED
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "knowledge_sources"
