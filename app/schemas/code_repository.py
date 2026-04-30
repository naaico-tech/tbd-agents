"""Pydantic schemas for the CodeRepository API."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.code_repository import (
    DEFAULT_EXCLUDE_GLOBS,
    DEFAULT_INCLUDE_GLOBS,
    CodeRepositoryStatus,
)


class IndexingConfigSchema(BaseModel):
    enabled: bool = True
    include_globs: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE_GLOBS))
    exclude_globs: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    max_file_kb: int = 256
    chunk_chars: int = 1200
    overlap_chars: int = 150


class CodeRepositoryCreate(BaseModel):
    name: str
    description: str = ""
    repo_url: str
    default_branch: str = "main"
    token_name: str | None = None
    tags: list[str] = []
    indexing: IndexingConfigSchema | None = None


class CodeRepositoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repo_url: str | None = None
    default_branch: str | None = None
    token_name: str | None = None
    tags: list[str] | None = None
    indexing: IndexingConfigSchema | None = None


class CodeRepositoryResponse(BaseModel):
    id: str
    name: str
    description: str
    repo_url: str
    default_branch: str
    token_name: str | None
    tags: list[str]
    status: CodeRepositoryStatus
    last_synced_at: datetime | None
    last_indexed_at: datetime | None
    last_commit_sha: str | None
    last_error: str | None
    local_path: str | None
    indexing: IndexingConfigSchema
    vector_collection: str | None
    file_count: int
    chunk_count: int
    github_user: str
    created_at: datetime
    updated_at: datetime


class CodeRepositorySearchRequest(BaseModel):
    query: str
    limit: int | None = None


class CodeRepositorySearchResult(BaseModel):
    repo_id: str
    repo_name: str
    file_path: str
    line_start: int
    line_end: int
    score: float
    text: str


class CodeRepositorySearchResponse(BaseModel):
    results: list[CodeRepositorySearchResult]


class CodeRepositorySyncResponse(BaseModel):
    status: CodeRepositoryStatus
    local_path: str | None
    last_commit_sha: str | None
    last_error: str | None = None


class CodeRepositoryIndexResponse(BaseModel):
    status: CodeRepositoryStatus
    indexed: bool
    file_count: int
    chunk_count: int
    reason: str | None = None
    last_error: str | None = None
