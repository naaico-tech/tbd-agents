from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.knowledge_item import KnowledgeContentType
from app.models.knowledge_source import KnowledgeSourceStatus, KnowledgeSourceType


# ── KnowledgeSource schemas ──────────────────────────────────────────────────


class KnowledgeSourceCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "My Qdrant DB",
                    "description": "Qdrant vector store",
                    "source_type": "vector_db",
                    "connection_config": {
                        "url": "http://localhost:6333",
                        "collection": "my_collection",
                        "api_key_token_name": "QDRANT_API_KEY",
                    },
                    "tags": ["qdrant"],
                },
                {
                    "name": "My pgvector DB",
                    "description": "PostgreSQL pgvector source",
                    "source_type": "pgvector",
                    "connection_config": {
                        "dsn": "postgresql+asyncpg://user:pass@host:5432/dbname",
                        "collection": "my_collection",
                        "dsn_token_name": "MY_PG_TOKEN",
                    },
                    "tags": ["pgvector"],
                },
                {
                    "name": "My MongoDB store",
                    "description": "Local MongoDB / GridFS knowledge store",
                    "source_type": "mongo_db",
                    "connection_config": {},
                    "tags": ["mongo"],
                },
            ]
        }
    )

    name: str
    description: str = ""
    source_type: KnowledgeSourceType
    connection_config: dict[str, Any] = {}
    tags: list[str] = []


class KnowledgeSourceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_type: KnowledgeSourceType | None = None
    connection_config: dict[str, Any] | None = None
    tags: list[str] | None = None


class KnowledgeSourceResponse(BaseModel):
    id: str
    name: str
    description: str
    source_type: KnowledgeSourceType
    connection_config: dict[str, Any]
    tags: list[str]
    status: KnowledgeSourceStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceTestResponse(BaseModel):
    success: bool
    error: str | None = None


# ── KnowledgeItem schemas ────────────────────────────────────────────────────


class KnowledgeItemCreate(BaseModel):
    source_id: str
    name: str
    content_type: KnowledgeContentType = KnowledgeContentType.TEXT
    text_content: str | None = None
    tags: list[str] = []
    metadata: dict[str, Any] = {}


class KnowledgeItemUpdate(BaseModel):
    name: str | None = None
    text_content: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeItemResponse(BaseModel):
    id: str
    source_id: str
    name: str
    content_type: KnowledgeContentType
    text_content: str | None
    file_id: str | None
    file_name: str | None
    file_size: int | None
    mime_type: str | None
    tags: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class KnowledgeQueryRequest(BaseModel):
    tags: list[str]
    limit: int = 10


class KnowledgeQueryResponse(BaseModel):
    items: list[KnowledgeItemResponse]
