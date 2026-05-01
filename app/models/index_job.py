"""IndexJob Beanie document — async envelope for code-repository indexing.

A separate document (rather than fields on ``CodeRepository``) so that:

* multiple concurrent jobs per repo are safe and independently observable;
* job history is preserved for audit / debugging;
* HTTP-shaped status (``syncing/indexed/error``) is decoupled from rich job
  telemetry (counters, phase, current_file, ETA, …).
"""

from datetime import UTC, datetime
from typing import Literal

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field
from pymongo import ASCENDING, IndexModel


class IndexJobCounters(BaseModel):
    files_total: int = 0
    files_done: int = 0
    files_failed: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    bytes_done: int = 0
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0


class IndexJobError(BaseModel):
    message: str
    traceback: str | None = None


JobState = Literal[
    "queued",
    "discovering",
    "hashing",
    "embedding",
    "upserting",
    "committed",
    "done",
    "failed",
    "cancelled",
]
JobKind = Literal["full", "incremental"]

TERMINAL_STATES: set[str] = {"done", "failed", "cancelled"}


class IndexJob(Document):
    repo_id: PydanticObjectId
    kind: JobKind = "full"
    state: JobState = "queued"
    current_phase: str = "queued"
    current_file: str | None = None
    counters: IndexJobCounters = Field(default_factory=IndexJobCounters)
    head_commit_sha: str | None = None
    base_commit_sha: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    eta_seconds: float | None = None
    error: IndexJobError | None = None
    shard_count: int = 1
    shards_done: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "index_jobs"
        indexes = [
            IndexModel([("repo_id", ASCENDING), ("state", ASCENDING)]),
            IndexModel([("repo_id", ASCENDING), ("head_commit_sha", ASCENDING)]),
            IndexModel([("created_at", ASCENDING)]),
        ]
