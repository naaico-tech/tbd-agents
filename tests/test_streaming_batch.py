"""Tests for the streaming batch pipeline (PR3 ``streaming-batch-pipeline``).

These tests exercise the cross-file batching invariants of
:meth:`CodeRepositoryManager.index_changes`:

* Number of embed calls = ``ceil(total_chunks / EMBED_BATCH_SIZE)``.
* Per-file ``IndexedFile.chunk_ids`` are the contiguous slice of point ids
  emitted for that file (correct file→chunk partition).
* Mid-shard cancellation flag stops processing before the next batch.
* Memory ceiling: at no point does the pipeline hold more than
  ``EMBED_BATCH_SIZE`` chunk texts simultaneously.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.code_repository import CodeRepositoryStatus, IndexingConfig
from app.services.code_repository_manager import (
    CodeRepositoryManager,
    FileChange,
    Manifest,
    _point_id,
)

FAKE_REPO_ID = "6601a1b2c3d4e5f607890abc"


# ── Fixtures (mirror tests/test_indexing_pipeline.py) ────────────────────────


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
        # Tiny chunks so we can pack many per file without huge fixtures.
        indexing=IndexingConfig(chunk_chars=10, overlap_chars=0),
        vector_collection="code_test",
        file_count=0,
        chunk_count=0,
        updated_at=None,
        save=AsyncMock(),
    )


@pytest.fixture()
def patch_qdrant():
    client = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    client.create_collection = AsyncMock()
    client.delete_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    with patch("qdrant_client.AsyncQdrantClient", return_value=client):
        yield client


@pytest.fixture()
def patch_embeddings(monkeypatch):
    """Replace the embed helper with a counter that records every batch size.

    Returns ``stats`` dict carrying ``calls`` (list of batch sizes seen) and
    ``max_batch`` (largest single batch encountered) so tests can assert both
    the number of embed calls and the memory-ceiling invariant.
    """
    from app.services import code_repository_manager as mod

    stats: dict = {"calls": [], "max_batch": 0}

    async def _embed_many(texts):
        n = len(texts)
        stats["calls"].append(n)
        if n > stats["max_batch"]:
            stats["max_batch"] = n
        return [[0.1, 0.2, 0.3] for _ in texts]

    monkeypatch.setattr(mod.settings, "embeddings_enabled", True)
    monkeypatch.setattr(mod.settings, "embeddings_dim", 3)
    monkeypatch.setattr(
        mod.embeddings_service,
        "embed_many",
        AsyncMock(side_effect=_embed_many),
    )
    return stats


@pytest.fixture()
def patch_indexed_file(monkeypatch):
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

    monkeypatch.setattr(mod, "_find_indexed_file", _find)
    monkeypatch.setattr(mod, "_upsert_indexed_file", _upsert)
    monkeypatch.setattr(mod, "_record_indexed_file_error", _err)

    class _AsyncIter:
        def __init__(self, items):
            self._items = list(items)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if not self._items:
                raise StopAsyncIteration
            return self._items.pop(0)

    fake_cls = MagicMock()
    fake_cls.find = MagicMock(return_value=SimpleNamespace(
        count=AsyncMock(side_effect=lambda: len(store)),
        __aiter__=lambda self: _AsyncIter(list(store.values())).__aiter__(),
    ))
    monkeypatch.setattr(mod, "IndexedFile", fake_cls)
    return store


def _force_batch_size(monkeypatch, value: int) -> None:
    """Override ``EMBED_BATCH_SIZE`` for the duration of a test."""
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod, "EMBED_BATCH_SIZE", value)


# ── 1. Embed-call count for a single 1000-chunk file ─────────────────────────


@pytest.mark.asyncio
async def test_single_large_file_uses_ceil_div_embed_calls(
    monkeypatch, tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    """1000 chunks @ batch=128 → exactly 8 embed calls (ceil(1000/128))."""
    _force_batch_size(monkeypatch, 128)

    # chunk_chars=10, overlap=0 → 1000 chunks for a 10000-char file.
    big = "x" * 10_000
    (tmp_path / "big.py").write_text(big)

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="h",
        base_sha=None,
        changes=[FileChange(
            path="big.py", blob_sha="sha-BIG", change="added", size=10_000
        )],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result["indexed"] is True
    assert result["chunks_done"] == 1000
    # 1000 / 128 = 7.8125 → 8 batches.
    assert len(patch_embeddings["calls"]) == 8
    assert sum(patch_embeddings["calls"]) == 1000
    # All but the last batch should be exactly EMBED_BATCH_SIZE.
    assert patch_embeddings["calls"][:-1] == [128] * 7
    assert patch_embeddings["calls"][-1] == 1000 - 7 * 128

    # IndexedFile.chunk_ids = the 1000 deterministic ids in order.
    stored = patch_indexed_file[(FAKE_REPO_ID, "big.py")]
    expected_ids = [
        _point_id(FAKE_REPO_ID, "big.py", i, "sha-BIG") for i in range(1000)
    ]
    assert stored.chunk_ids == expected_ids
    assert stored.n_chunks == 1000


# ── 2. Cross-file batching: 5 × 50-chunk files coalesce into 2 batches ───────


@pytest.mark.asyncio
async def test_cross_file_batching_partitions_chunk_ids(
    monkeypatch, tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    """5 files × 50 chunks @ batch=128 → 2 embed calls; per-file ids correct."""
    _force_batch_size(monkeypatch, 128)

    file_names = [f"f{i}.py" for i in range(5)]
    for name in file_names:
        (tmp_path / name).write_text("y" * 500)  # 500/10 = 50 chunks each

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="h",
        base_sha=None,
        changes=[
            FileChange(
                path=name, blob_sha=f"sha-{name}", change="added", size=500
            )
            for name in file_names
        ],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result["indexed"] is True
    assert result["added"] == 5
    assert result["chunks_done"] == 250
    # 250 chunks / batch 128 → 2 calls (128 + 122).
    assert len(patch_embeddings["calls"]) == 2
    assert sum(patch_embeddings["calls"]) == 250

    # Each file's IndexedFile row carries its own 50 deterministic ids in order.
    for name in file_names:
        stored = patch_indexed_file[(FAKE_REPO_ID, name)]
        expected = [
            _point_id(FAKE_REPO_ID, name, i, f"sha-{name}") for i in range(50)
        ]
        assert stored.chunk_ids == expected
        assert stored.n_chunks == 50


# ── 3. Cancellation between batches ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_cancellation_stops_before_next_batch(
    monkeypatch, tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    """Setting the cancel flag after batch #1 must prevent batch #2 entirely."""
    _force_batch_size(monkeypatch, 128)

    # 1000 chunks → 8 batches normally. Cancel after the first.
    (tmp_path / "big.py").write_text("z" * 10_000)

    from app.services import code_repository_manager as mod

    cancel_state = {"flag": False}

    def _is_cancelled(_job_id):
        return cancel_state["flag"]

    monkeypatch.setattr(
        mod.index_progress, "is_cancelled_sync", _is_cancelled
    )
    monkeypatch.setattr(
        mod.index_progress, "incr_sync", lambda *a, **k: None
    )
    monkeypatch.setattr(
        mod.index_progress, "set_phase_sync", lambda *a, **k: None
    )

    # After the FIRST embed call, flip the cancel flag so the next inner-loop
    # check (between batches) bails out.
    real_embed = mod.embeddings_service.embed_many.side_effect

    async def _embed_then_cancel(texts):
        out = await real_embed(texts)
        cancel_state["flag"] = True
        return out

    mod.embeddings_service.embed_many = AsyncMock(
        side_effect=_embed_then_cancel
    )

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="h",
        base_sha=None,
        changes=[FileChange(
            path="big.py", blob_sha="sha-BIG", change="added", size=10_000
        )],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest, job_id="JOB-X")

    assert result["indexed"] is True
    # Only the first batch ran — no further embed/upsert calls.
    assert len(patch_embeddings["calls"]) == 1
    assert patch_qdrant.upsert.await_count == 1
    # File never finalized → no IndexedFile row written for big.py.
    assert (FAKE_REPO_ID, "big.py") not in patch_indexed_file


# ── 4. Memory ceiling: never more than EMBED_BATCH_SIZE texts in flight ─────


@pytest.mark.asyncio
async def test_memory_ceiling_never_exceeds_batch_size(
    monkeypatch, tmp_path, patch_qdrant, patch_embeddings, patch_indexed_file
):
    """Even with 5 files × 200 chunks, no single embed batch exceeds 128."""
    _force_batch_size(monkeypatch, 128)

    for i in range(5):
        # 200 chunks per file × 5 files = 1000 chunks total.
        (tmp_path / f"f{i}.py").write_text("q" * 2000)

    repo = _repo(str(tmp_path))
    manifest = Manifest(
        head_sha="h",
        base_sha=None,
        changes=[
            FileChange(
                path=f"f{i}.py", blob_sha=f"s{i}",
                change="added", size=2000,
            )
            for i in range(5)
        ],
    )

    mgr = CodeRepositoryManager()
    result = await mgr.index_changes(repo, manifest)

    assert result["chunks_done"] == 1000
    assert patch_embeddings["max_batch"] <= 128
    # And every batch except possibly the last was exactly the ceiling.
    assert all(n <= 128 for n in patch_embeddings["calls"])
    # Total chunks across all batches matches.
    assert sum(patch_embeddings["calls"]) == 1000
