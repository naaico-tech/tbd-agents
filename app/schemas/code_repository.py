"""Pydantic schemas for the CodeRepository API."""

from datetime import datetime

from pydantic import BaseModel

from app.models.code_repository import CodeRepositoryStatus


class CodeRepositoryCreate(BaseModel):
    name: str
    description: str = ""
    repo_url: str
    default_branch: str = "main"
    token_name: str | None = None
    tags: list[str] = []


class CodeRepositoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    repo_url: str | None = None
    default_branch: str | None = None
    token_name: str | None = None
    tags: list[str] | None = None


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
    file_count: int
    gitnexus_job_id: str | None
    github_user: str
    created_at: datetime
    updated_at: datetime


class CodeRepositorySyncResponse(BaseModel):
    status: CodeRepositoryStatus
    local_path: str | None
    last_commit_sha: str | None
    last_error: str | None = None


class CodeRepositoryIndexResponse(BaseModel):
    status: CodeRepositoryStatus
    indexed: bool
    file_count: int
    gitnexus_job_id: str | None = None
    reason: str | None = None
    last_error: str | None = None
