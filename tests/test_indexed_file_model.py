"""Tests for the IndexedFile Beanie document (pure model construction)."""

import json
from datetime import UTC, datetime

from beanie import PydanticObjectId

from app.models.indexed_file import IndexedFile


class TestIndexedFileModel:
    def test_defaults(self):
        repo_id = PydanticObjectId()
        before = datetime.now(UTC)
        f = IndexedFile.model_construct(
            repo_id=repo_id,
            file_path="src/app/main.py",
            blob_sha="a" * 40,
        )
        default_indexed_at = IndexedFile.model_fields["indexed_at"].default_factory()
        after = datetime.now(UTC)

        assert f.repo_id == repo_id
        assert f.file_path == "src/app/main.py"
        assert f.blob_sha == "a" * 40
        assert IndexedFile.model_fields["chunk_ids"].default_factory() == []
        assert IndexedFile.model_fields["n_chunks"].default == 0
        assert IndexedFile.model_fields["size_bytes"].default == 0
        assert IndexedFile.model_fields["language"].default is None
        assert IndexedFile.model_fields["error"].default is None

        # indexed_at default factory yields a recent UTC datetime.
        assert default_indexed_at.tzinfo is not None
        assert before <= default_indexed_at <= after

    def test_custom_values(self):
        repo_id = PydanticObjectId()
        f = IndexedFile.model_construct(
            repo_id=repo_id,
            file_path="lib/x.ts",
            blob_sha="b" * 40,
            chunk_ids=["p1", "p2", "p3"],
            n_chunks=3,
            size_bytes=4096,
            language="typescript",
            error=None,
        )
        assert f.chunk_ids == ["p1", "p2", "p3"]
        assert f.n_chunks == 3
        assert f.size_bytes == 4096
        assert f.language == "typescript"

    def test_model_dump_json_serializable(self):
        f = IndexedFile.model_construct(
            repo_id=PydanticObjectId(),
            file_path="README.md",
            blob_sha="c" * 40,
            chunk_ids=["pt-1"],
            n_chunks=1,
            size_bytes=128,
            language="markdown",
            indexed_at=datetime.now(UTC),
        )
        dumped = f.model_dump(mode="json")
        # Must round-trip through json.dumps without a custom encoder.
        encoded = json.dumps(dumped)
        decoded = json.loads(encoded)
        assert decoded["file_path"] == "README.md"
        assert decoded["blob_sha"] == "c" * 40
        assert decoded["n_chunks"] == 1
        assert decoded["chunk_ids"] == ["pt-1"]
        assert decoded["language"] == "markdown"

    def test_settings_indexes(self):
        assert IndexedFile.Settings.name == "indexed_files"
        index_names = {idx.document["name"] for idx in IndexedFile.Settings.indexes}
        assert "uq_repo_file" in index_names
