import os as _os
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

_POSTGRES = _os.environ.get("DB_BACKEND", "mongo").lower() == "postgres"

if _POSTGRES:
    from pydantic import BaseModel as _PyBase
    from pydantic import Field as _PgField

    from app.db_postgres import PostgresDocument as _PgBase

    class _DocumentBase(_PgBase, _PyBase):  # type: ignore[misc]
        id: str | None = _PgField(default=None)

else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]


class CodeGraphRepoStatus(StrEnum):
    PENDING = "pending"
    CLONING = "cloning"
    INDEXING = "indexing"
    READY = "ready"
    ERROR = "error"


class CodeGraphRepo(_DocumentBase):  # type: ignore[valid-type]
    name: str  # human label, e.g. "tbd-agents"
    repo_url: str  # https://github.com/org/repo
    local_path: str = ""  # absolute path on disk (filled in by service)
    status: CodeGraphRepoStatus = CodeGraphRepoStatus.PENDING
    indexed_at: datetime | None = None
    error_message: str | None = None
    agent_ids: list[str] = Field(default_factory=list)  # which agents have access
    mcp_server_id: str | None = None  # the McpServer record ID for this repo
    celery_task_id: str | None = None  # running Celery task ID for progress tracking
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "codegraph_repos"
