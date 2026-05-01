"""Tests for the per-file incremental indexing pipeline.

Covers:
* deterministic point-id generation (``_point_id``);
* first-time + incremental flows of ``CodeRepositoryManager.index_changes``
  with mocked Qdrant + embeddings;
* ``_ensure_collection`` only creates when missing — never drops.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.code_repository import CodeRepositoryStatus, IndexingConfig
from app.services.code_repository_manager import (
    NS_REPO,
    CodeRepositoryManager,
    FileChange,
    Manifest,
    _ensure_collection,
    _point_id,
)

FAKE_REPO_ID = "6601a1b2c3d4e5f607890abc"


# ── Deterministic point IDs ───────────────────────────────────────────────


def test_point_id_is_deterministic():
    a = _point_id("r1", "src/a.py", 0, "sha1")
    b = _point_id("r1", "src/a.py", 0, "sha1")
    assert a == b


def test_point_id_changes_with_chunk_index():
    assert _point_id("r1", "x", 0, "sha") != _point_id("r1", "x", 1, "sha")


def test_point_id_changes_with_blob_sha():
    assert _point_id("r1", "x", 0, "old") != _point_id("r1", "x", 0, "new")


def test_point_id_changes_with_repo_id_and_path():
    assert _point_id("r1", "x", 0, "s") != _point_id("r2", "x", 0, "s")
    assert _point_id("r1", "x", 0, "s") != _point_id("r1", "y", 0, "s")


def test_point_id_namespace_is_stable_constant():
    # Hard-coded — never change without invalidating every persisted id.
    assert str(NS_REPO) == "6e0c1c4e-7c85-4f4c-9f3a-1f4c4a1f4c4a"


# ── _ensure_collection ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ensure_collection_creates_when_missing():
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=False)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()

    await _ensure_collection(client, "code_x", 384)

    client.create_collection.assert_awaited_once()
    # Two payload indexes attempted (best-effort).
    assert client.create_payload_index.await_count == 2


@pytest.mark.asyncio
async def test_ensure_collection_skips_create_when_present():
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()

    await _ensure_collection(client, "code_x", 384)

    client.create_collection.assert_not_awaited()


# ── Pipeline fixtures ─────────────────────────────────────────────────────


def _repo(local_path: str):
    return SimpleNamespace(
        id=FAKE_REPO_ID,
        name="r",
        repo_url="https://github.com/x/y",
        default_branch="main",
        token_name=None,
        status=CodeRepositoryStatus.SYNCED,
        last_synced_at=None,
        last_indexed_at=None,
        last_commit_sha=None,
        last_error=None,
        local_path=local_path,
        indexing=IndexingConfig(),
        vector_collection="code_test",
        file_count=0,
        chunk_count=0,
        updated_at=None,
        save=AsyncMock(),
    )


@pytest.fixture()
def patch_qdrant():
    """Patch ``qdrant_client.AsyncQdrantClient`` to return a mock client."""
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.create_collection = AsyncMock()
    client.delete_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    with patch(
        "qdrant_client.AsyncQdrantClient", return_value=client
    ):
        yield client


@pytest.fixture()
def patch_embeddings(monkeypatch):
    from app.services import code_repository_manager as mod

    # Each call returns one tiny vector per input chunk.
    async def _embed_many(texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(mod.settings, "embeddings_enabled", True)
    monkeypatch.setattr(mod.settings, "embeddings_dim", 3)
    monkeypatch.setattr(
        mod.embeddings_service, "embed_many", AsyncMock(side_effect=_embed_many)
    )


@pytest.fixture()
def patch_indexed_file(monkeypatch):
    """In-memory IndexedFile store keyed by (repo_id, file_path)."""
    from app.services import code_repository_manager as mod

    store: dict[tuple[str, str], MagicMock] = {}

    async def _find(repo_id, file_path):
        return store.get((str(repo_id), file_path))

    async def _upsert(*, repo_id, file_path, blob_sha, chunk_ids,
                      n_chunks, size_bytes):
        key = (str(repo_id), file_path)
        doc = MagicMock()
        doc.repo_id = repo_id
        doc.file_path = file_path
        doc.blob_sha = blob_sha
        doc.chunk_ids = list(chunk_ids)
        doc.n_chunks = n_chunks
        doc.size_bytes = size_bytes
        doc.delete = AsyncMock(side_effect=lambda: store.pop(key, None))
        store[key] = doc

    async def _err(repo_id, file_path, blob_sha, error):
        key = (str(repo_id), file_path)
        doc = store.get(key) or MagicMock(chunk_ids=[], n_chunks=0)
        doc.error = error
        doc.delete = AsyncMock(side_effect=lambda: store.pop(key, None))
        store[key] = doc

    # Bypass the count/find used by _finalize_repo.
    fake_find = MagicMock()
    fake_find.return_value.count = AsyncMock(side_effect=lambda: len(store))

    class _AsyncIter:
        def __init__(self, items):
            self._items = list(items)
        def __aiter__(self):
            return self
        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    fake_find.return_value.__aiter__ = lambda self: _AsyncIter(
        list(store.values())
    ).__aiter__()
    # Beanie find returns an object both awaitable-iterable AND with .count;
    # patch the IndexedFile class symbol used inside the module.
    monkeypatch.setattr(mod, "_find_indexed_file", _find)
    monkeypatch.setattr(mod, "_upsert_indexed_file", _upsert)
    monkeypatch.setattr(mod, "_record_indexed_file_error", _err)

    fake_cls = MagicMock()
    fake_cls.find = MagicMock(return_value=SimpleNamespace(
        count=AsyncMock(side_effect=lambda: len(store)),
        __aiter__=lambda self: _AsyncIter(list(store.values())).__aiter__(),
    ))
    monkeypatch.setattr(mod, "IndexedFile", fake_cls)
    return store


# ── First-time index ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_first_time_indexes_added_files(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    # Three real files on disk so read_text works.
    for name in ("a.py", "b.py", "c.py"):
        (tmp_path / name).write_text(f"print('{name}')\n")

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="head1",
        base_sha=None,
        changes=[
            FileChange(path="a.py", blob_sha="sa", change="added", size=10),
            FileChange(path="b.py", blob_sha="sb", change="added", size=10),
            FileChange(path="c.py", blob_sha="sc", change="added", size=10),
        ],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result["indexed"] is True
    assert result["added"] == 3
    assert result["modified"] == 0
    assert result["deleted"] == 0
    # Three IndexedFile rows persisted.
    assert len(patch_indexed_file) == 3
    # Qdrant: collection exists (mocked True) → no create. NEVER dropped.
    patch_qdrant.delete_collection.assert_not_awaited()
    # Streaming pipeline (PR3): all three single-chunk files coalesce into ONE
    # cross-file batch (default EMBED_BATCH_SIZE=128 ≫ 3 chunks).
    assert patch_qdrant.upsert.await_count == 1
    upserted_points = patch_qdrant.upsert.await_args.kwargs["points"]
    assert len(upserted_points) == 3
    # Final state mirrors back.
    assert repo.last_commit_sha == "head1"
    assert repo.status == CodeRepositoryStatus.INDEXED


@pytest.mark.asyncio
async def test_index_uses_deterministic_point_ids(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    (tmp_path / "a.py").write_text("print('hi')\n")
    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="head1",
        base_sha=None,
        changes=[FileChange(path="a.py", blob_sha="sha-A", change="added", size=10)],
    )

    mgr = CodeRepositoryManager()
    await mgr.index_changes(repo, manifest)

    points = patch_qdrant.upsert.await_args.kwargs["points"]
    assert len(points) == 1
    expected = _point_id(FAKE_REPO_ID, "a.py", 0, "sha-A")
    assert points[0].id == expected
    # Stored chunk_ids match what was upserted.
    stored = patch_indexed_file[(FAKE_REPO_ID, "a.py")]
    assert stored.chunk_ids == [expected]


@pytest.mark.asyncio
async def test_idempotent_rerun_yields_same_ids(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    (tmp_path / "a.py").write_text("print('hi')\n")
    repo = _repo(str(tmp_path))
    change = FileChange(path="a.py", blob_sha="sha-A", change="added", size=10)
    manifest = Manifest(head_sha="h", base_sha=None, changes=[change])

    mgr = CodeRepositoryManager()
    await mgr.index_changes(repo, manifest)
    first_ids = list(patch_indexed_file[(FAKE_REPO_ID, "a.py")].chunk_ids)

    # Re-run with same blob_sha → same ids, no stale-delete needed.
    patch_qdrant.upsert.reset_mock()
    patch_qdrant.delete.reset_mock()
    await mgr.index_changes(repo, manifest)
    second_ids = list(patch_indexed_file[(FAKE_REPO_ID, "a.py")].chunk_ids)

    assert first_ids == second_ids
    # No stale delete because new ids fully overlap old ones.
    patch_qdrant.delete.assert_not_awaited()


# ── Incremental: modify + delete + add ────────────────────────────────────


@pytest.mark.asyncio
async def test_incremental_modify_delete_add(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    # Pre-populate three files on disk and three IndexedFile rows.
    for name in ("A.py", "B.py", "C.py"):
        (tmp_path / name).write_text(f"v = '{name}'\n")
    (tmp_path / "D.py").write_text("v = 'D'\n")  # new file added

    # Seed pre-existing IndexedFile state so "modified" + "deleted" have
    # something to delete.
    from app.services import code_repository_manager as mod

    seed_a_old_id = _point_id(FAKE_REPO_ID, "A.py", 0, "sha-A-OLD")
    seed_b_old_id = _point_id(FAKE_REPO_ID, "B.py", 0, "sha-B-OLD")
    seed_c_old_id = _point_id(FAKE_REPO_ID, "C.py", 0, "sha-C-OLD")
    for path, old_id in (
        ("A.py", seed_a_old_id),
        ("B.py", seed_b_old_id),
        ("C.py", seed_c_old_id),
    ):
        await mod._upsert_indexed_file(
            repo_id=FAKE_REPO_ID,
            file_path=path,
            blob_sha="sha-OLD",
            chunk_ids=[old_id],
            n_chunks=1,
            size_bytes=10,
        )

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="head2",
        base_sha="head1",
        changes=[
            FileChange(path="A.py", blob_sha="sha-A-NEW", change="modified", size=10),
            FileChange(path="B.py", blob_sha="", change="deleted", size=0),
            FileChange(path="D.py", blob_sha="sha-D-NEW", change="added", size=10),
        ],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    # Counters.
    assert result["modified"] == 1
    assert result["deleted"] == 1
    assert result["added"] == 1
    # A & D upserted in a single coalesced batch (PR3 streaming pipeline).
    assert patch_qdrant.upsert.await_count == 1
    assert len(patch_qdrant.upsert.await_args.kwargs["points"]) == 2
    # Stale-delete fired for A (modified) and B (deleted) — both delete().
    assert patch_qdrant.delete.await_count == 2
    # IndexedFile rows: A modified, B removed, C untouched, D inserted.
    assert (FAKE_REPO_ID, "A.py") in patch_indexed_file
    assert (FAKE_REPO_ID, "B.py") not in patch_indexed_file
    assert (FAKE_REPO_ID, "C.py") in patch_indexed_file
    assert (FAKE_REPO_ID, "D.py") in patch_indexed_file
    a_row = patch_indexed_file[(FAKE_REPO_ID, "A.py")]
    assert a_row.blob_sha == "sha-A-NEW"
    assert a_row.chunk_ids == [
        _point_id(FAKE_REPO_ID, "A.py", 0, "sha-A-NEW")
    ]
    # No collection drop.
    patch_qdrant.delete_collection.assert_not_awaited()
    assert repo.last_commit_sha == "head2"


# ── No-op: empty manifest fast-path ───────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_manifest_short_circuits(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    repo = _repo(str(tmp_path))
    manifest = Manifest(head_sha="h2", base_sha="h1", changes=[])
    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result == {
        "indexed": True,
        "added": 0,
        "modified": 0,
        "deleted": 0,
        "chunks_done": 0,
        "files_failed": 0,
    }
    patch_qdrant.upsert.assert_not_awaited()
    patch_qdrant.delete_collection.assert_not_awaited()
    assert repo.last_commit_sha == "h2"
    assert repo.status == CodeRepositoryStatus.INDEXED


# ── Poison pill: undecodable bytes do not abort the job ────────────────────


@pytest.mark.asyncio
async def test_undecodable_file_marked_failed(
    tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    bad = tmp_path / "binary.py"
    bad.write_bytes(b"\xff\xfe\x00\x01not utf8")
    (tmp_path / "good.py").write_text("v = 1\n")

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="h",
        base_sha=None,
        changes=[
            FileChange(path="binary.py", blob_sha="sb", change="added", size=10),
            FileChange(path="good.py", blob_sha="sg", change="added", size=10),
        ],
    )
    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result["files_failed"] == 1
    assert result["added"] == 1
    # The bad file did NOT crash the pipeline.
    assert repo.status == CodeRepositoryStatus.INDEXED


# ── Compatibility shim: ``index()`` delegates to ``index_changes()`` ──────


@pytest.mark.asyncio
async def test_index_compat_shim_calls_index_changes(
    tmp_path, monkeypatch, patch_qdrant, patch_embeddings, patch_indexed_file
):
    """Old callers of ``index()`` keep working via the discover→delegate path."""
    from app.services import code_repository_manager as mod

    # Ensure gitnexus is disabled so the embedding pipeline path is exercised.
    monkeypatch.setattr(mod.settings, "gitnexus_url", None)

    (tmp_path / "a.py").write_text("v = 1\n")
    repo = _repo(str(tmp_path))
    repo.last_commit_sha = "deadbeef"  # short-circuits rev-parse

    mgr = CodeRepositoryManager()
    fake_manifest = Manifest(
        head_sha="deadbeef",
        base_sha=None,
        changes=[FileChange(path="a.py", blob_sha="sa", change="added", size=10)],
    )

    with patch(
        "app.services.code_repository_manager.discover_changes",
        new=AsyncMock(return_value=fake_manifest),
    ):
        result = await mgr.index(repo)

    assert result["indexed"] is True
    # Compat fields are present for legacy callers.
    assert "file_count" in result
    assert "chunk_count" in result
