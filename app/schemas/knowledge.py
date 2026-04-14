from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.knowledge_item import KnowledgeContentType
from app.models.knowledge_source import KnowledgeSourceStatus, KnowledgeSourceType


# ── KnowledgeSource schemas ──────────────────────────────────────────────────


class KnowledgeSourceCreate(BaseModel):
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
