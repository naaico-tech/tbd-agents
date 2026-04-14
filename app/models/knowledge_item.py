from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import Field


class KnowledgeContentType(StrEnum):
    TEXT = "text"
    FILE = "file"
    IMAGE = "image"


class KnowledgeItem(Document):
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
