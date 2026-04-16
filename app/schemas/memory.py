from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models.memory import MemoryScope


class MemoryCreate(BaseModel):
    agent_id: str
    scope: MemoryScope
    key: str
    value: str
    embedding: list[float] | None = None
    metadata: dict[str, Any] = {}
    ttl: datetime | None = None


class MemoryUpdate(BaseModel):
    scope: MemoryScope | None = None
    key: str | None = None
    value: str | None = None
    embedding: list[float] | None = None
    metadata: dict[str, Any] | None = None
    ttl: datetime | None = None


class MemoryResponse(BaseModel):
    id: str
    agent_id: str
    scope: MemoryScope
    key: str
    value: str
    embedding: list[float] | None
    metadata: dict[str, Any]
    ttl: datetime | None
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(BaseModel):
    agent_id: str
    query: str
    scope: MemoryScope | None = None
    limit: int = 10
