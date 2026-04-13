from datetime import datetime

from pydantic import BaseModel

# ── KnowledgeBase ─────────────────────────────────────────────────────────────


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str = ""
    tags: list[str] = []


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime


# ── KnowledgeChunk ────────────────────────────────────────────────────────────


class KnowledgeChunkCreate(BaseModel):
    content: str
    source: str = ""


class KnowledgeChunkUpdate(BaseModel):
    content: str | None = None
    source: str | None = None


class KnowledgeChunkResponse(BaseModel):
    id: str
    knowledge_base_id: str
    content: str
    source: str
    created_at: datetime
    updated_at: datetime
