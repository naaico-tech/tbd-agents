"""IndexedFile model: per-file record of what's currently indexed in Qdrant.

One document per (repo_id, file_path). Enables incremental re-indexing by
comparing current ``blob_sha`` (git OID) to the stored value: unchanged files
can be skipped, removed files can be evicted from Qdrant.
"""

from datetime import UTC, datetime

from beanie import Document, PydanticObjectId
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class IndexedFile(Document):
    repo_id: PydanticObjectId
    file_path: str  # repo-relative POSIX path
    blob_sha: str  # git blob OID — content-addressed
    chunk_ids: list[str] = Field(default_factory=list)  # Qdrant point ids
    n_chunks: int = 0
    size_bytes: int = 0
    language: str | None = None  # filled in PR3
    indexed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: str | None = None  # if last attempt to index this file failed

    class Settings:
        name = "indexed_files"
        indexes = [
            IndexModel(
                [("repo_id", ASCENDING), ("file_path", ASCENDING)],
                unique=True,
                name="uq_repo_file",
            ),
            IndexModel([("repo_id", ASCENDING)]),
            IndexModel([("repo_id", ASCENDING), ("blob_sha", ASCENDING)]),
        ]
