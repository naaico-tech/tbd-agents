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


DEFAULT_INCLUDE_GLOBS: list[str] = [
    "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.go", "*.rs",
    "*.java", "*.kt", "*.swift", "*.rb", "*.cs", "*.cpp", "*.c",
    "*.h", "*.hpp", "*.md", "*.yml", "*.yaml", "*.json", "*.toml",
]

DEFAULT_EXCLUDE_GLOBS: list[str] = [
    "node_modules/**", ".venv/**", "dist/**", "build/**",
    ".git/**", "*.lock",
]


class IndexingConfig(BaseModel):
    """Per-repo indexing parameters."""

    enabled: bool = True
    include_globs: list[str] = Field(default_factory=lambda: list(DEFAULT_INCLUDE_GLOBS))
    exclude_globs: list[str] = Field(default_factory=lambda: list(DEFAULT_EXCLUDE_GLOBS))
    max_file_kb: int = 256
    chunk_chars: int = 1200
    overlap_chars: int = 150


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
    github_user: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "code_repositories"
