from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import Field


class KnowledgeSourceType(StrEnum):
    VECTOR_DB = "vector_db"
    MONGO_DB = "mongo_db"


class KnowledgeSourceStatus(StrEnum):
    REGISTERED = "registered"
    CONNECTED = "connected"
    ERROR = "error"


class KnowledgeSource(Document):
    name: str
    description: str = ""
    source_type: KnowledgeSourceType
    connection_config: dict = Field(default_factory=dict)  # vector_db: {url, collection, api_key_token_name}
    tags: list[str] = Field(default_factory=list)
    status: KnowledgeSourceStatus = KnowledgeSourceStatus.REGISTERED
    last_error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "knowledge_sources"
