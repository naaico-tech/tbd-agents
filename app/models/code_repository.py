"""CodeRepository model: registered codebases that can be synced + indexed.

A CodeRepository is a first-class resource (alongside skills, knowledge sources,
and MCP servers) that wraps a git repo with sync + semantic-index lifecycle.
Workflows attach repos via ``repository_ids`` and/or ``repository_tags``.
"""

from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import BaseModel, Field


class CodeRepositoryStatus(StrEnum):
    REGISTERED = "registered"
    SYNCING = "syncing"
    SYNCED = "synced"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR = "error"


class IndexingConfig(BaseModel):
    """Per-repo knobs that control which files are indexed and how they are chunked."""

    include_globs: list[str] = Field(default_factory=list)
    exclude_globs: list[str] = Field(default_factory=list)
    chunk_chars: int = 2000
    overlap_chars: int = 200
    max_file_kb: int = 256


class CodeRepository(Document):
    name: str
    description: str = ""
    repo_url: str
    default_branch: str = "main"
    token_name: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: CodeRepositoryStatus = CodeRepositoryStatus.REGISTERED
    last_synced_at: datetime | None = None
    last_indexed_at: datetime | None = None
    last_commit_sha: str | None = None
    last_error: str | None = None
    local_path: str | None = None
    indexing: IndexingConfig = Field(default_factory=IndexingConfig)
    vector_collection: str | None = None
    file_count: int = 0
    chunk_count: int = 0
    last_indexed_job_id: str | None = None
    gitnexus_job_id: str | None = None
    github_user: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "code_repositories"
