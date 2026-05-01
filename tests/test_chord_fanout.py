"""Tests for the chord-based shard fan-out orchestrator (PR3)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.models.code_repository import CodeRepositoryStatus, IndexingConfig
from app.models.index_job import IndexJobCounters
from app.services.code_repository_manager import FileChange, Manifest
from app.tasks import index_repository_task as task_mod

FAKE_REPO_ID = "6601a1b2c3d4e5f607890abc"
FAKE_JOB_ID = "6601a1b2c3d4e5f607890def"


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def fake_redis(monkeypatch):
    from app.services import index_progress as ip

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ip, "_redis", lambda: client)
    yield client


def _make_repo() -> SimpleNamespace:
    repo = SimpleNamespace(
        id=FAKE_REPO_ID,
        name="My Repo",
        repo_url="https://github.com/x/y",
        default_branch="main",
        token_name=None,
        status=CodeRepositoryStatus.SYNCED,
        last_synced_at=None,
        last_indexed_at=None,
        last_commit_sha="HEAD",
        last_error=None,
        local_path="/tmp/repo",
        indexing=IndexingConfig(),
        vector_collection=None,
        file_count=0,
        chunk_count=0,
        last_indexed_job_id=None,
        github_user="testuser",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save = AsyncMock()
    return repo


def _make_job(state: str = "queued") -> SimpleNamespace:
    job = SimpleNamespace(
        id=FAKE_JOB_ID,
        repo_id=FAKE_REPO_ID,
        kind="full",
        state=state,
        current_phase=state,
        current_file=None,
        counters=IndexJobCounters(),
        head_commit_sha="HEAD",
        base_commit_sha=None,
        started_at=None,
        finished_at=None,
        eta_seconds=None,
        error=None,
        shard_count=1,
        shards_done=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    job.save = AsyncMock()
    return job


# ── Sharding primitives ────────────────────────────────────────────────────


def test_shard_index_for_path_is_stable():
    """Same input → same shard idx; deterministic across calls."""
    a1 = task_mod._shard_index_for_path("src/foo/bar.py", 8)
    a2 = task_mod._shard_index_for_path("src/foo/bar.py", 8)
    assert a1 == a2
    assert 0 <= a1 < 8


def test_shard_count_respects_bounds(monkeypatch):
    monkeypatch.setattr(task_mod, "MAX_SHARDS", 16)
    monkeypatch.setattr(task_mod, "FILES_PER_SHARD", 50)
    assert task_mod._shard_count(0) == 0
    assert task_mod._shard_count(1) == 1
    assert task_mod._shard_count(50) == 1
    assert task_mod._shard_count(51) == 2
    assert task_mod._shard_count(50_000) == 16  # capped


def test_build_shards_partitions_changes_disjointly():
    changes = [
        FileChange(path=f"src/file_{i}.py", blob_sha=f"s{i}", change="added", size=1)
        for i in range(120)
    ]
    n = task_mod._shard_count(len(changes))  # 3
    shards = task_mod._build_shards(changes, n)
    assert len(shards) == n
    # Disjoint + total == 120
    seen: set[str] = set()
    for shard in shards:
        for item in shard:
            assert item["path"] not in seen
            seen.add(item["path"])
    assert seen == {c.path for c in changes}


# ── Orchestrator: empty manifest fast-path ─────────────────────────────────


def test_orchestrator_empty_manifest_does_not_launch_chord(fake_redis):
    repo = _make_repo()
    job = _make_job()

    finalize_repo_mock = AsyncMock(
        return_value={"file_count": 0, "chunk_count": 0, "last_commit_sha": "HEAD"}
    )
    chord_mock = MagicMock()

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.sync",
            new=AsyncMock(return_value="/tmp/repo"),
        ),
        patch(
            "app.services.code_repository_manager.discover_changes",
            new=AsyncMock(return_value=Manifest(head_sha="HEAD", base_sha="BASE")),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.finalize_repo",
            new=finalize_repo_mock,
        ),
        patch("app.tasks.index_repository_task.chord", chord_mock),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run(FAKE_JOB_ID, worker="t")
        )

    chord_mock.assert_not_called()
    finalize_repo_mock.assert_awaited_once()
    assert result["empty"] is True
    assert result["shard_count"] == 0
    assert job.state == "done"
    assert job.shard_count == 0


# ── Orchestrator: non-empty → chord with right shard count ─────────────────


def test_orchestrator_launches_chord_with_disjoint_shards(fake_redis):
    repo = _make_repo()
    job = _make_job()
    changes = [
        FileChange(path=f"a/{i}.py", blob_sha=f"b{i}", change="added", size=1)
        for i in range(60)
    ]
    manifest = Manifest(head_sha="HEAD", base_sha="BASE", changes=changes)

    chord_mock = MagicMock()
    chord_mock.return_value.apply_async.return_value = SimpleNamespace(id="C1")

    captured_groups: list = []

    def _capture_group(sigs):
        sigs = list(sigs)
        captured_groups.append(sigs)
        return MagicMock(name="group")

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.sync",
            new=AsyncMock(return_value="/tmp/repo"),
        ),
        patch(
            "app.services.code_repository_manager.discover_changes",
            new=AsyncMock(return_value=manifest),
        ),
        patch("app.tasks.index_repository_task.chord", chord_mock),
        patch("app.tasks.index_repository_task.group", _capture_group),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run(FAKE_JOB_ID, worker="t")
        )

    expected_n = task_mod._shard_count(60)  # 2 with default per-50
    assert result["shard_count"] == expected_n
    assert result["chord_id"] == "C1"
    assert job.state == "embedding"
    assert job.shard_count == expected_n
    chord_mock.return_value.apply_async.assert_called_once()
    # Sigs were captured — make sure each carries (job_id, shard_payload)
    sigs = captured_groups[0]
    assert len(sigs) == expected_n
    all_paths: set[str] = set()
    for sig in sigs:
        # Signature.args is a tuple — the second element is the shard payload.
        _, shard_payload = sig.args
        for item in shard_payload:
            assert item["path"] not in all_paths
            all_paths.add(item["path"])
    assert all_paths == {c.path for c in changes}


# ── index_shard task body ──────────────────────────────────────────────────


def test_index_shard_runs_index_changes_with_finalize_false(fake_redis):
    repo = _make_repo()
    job = _make_job(state="embedding")

    payload = [
        {"path": "x.py", "blob_sha": "sx", "change": "modified", "size": 1},
        {"path": "y.py", "blob_sha": "sy", "change": "added", "size": 2},
    ]

    expected = {
        "indexed": True,
        "added": 1,
        "modified": 1,
        "deleted": 0,
        "chunks_done": 7,
        "files_failed": 0,
    }
    index_changes_mock = AsyncMock(return_value=expected)

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.index_changes",
            new=index_changes_mock,
        ),
        patch(
            "app.services.index_progress.is_cancelled_sync",
            return_value=False,
        ),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run_shard(FAKE_JOB_ID, payload)
        )

    assert result["indexed"] is True
    assert result["added"] == 1
    assert result["modified"] == 1
    assert result["chunks_done"] == 7
    assert result["shard_size"] == 2
    assert result["cancelled"] is False
    # finalize must be False so shards don't race on repo summary.
    _, kwargs = index_changes_mock.call_args
    assert kwargs.get("finalize") is False
    assert kwargs.get("job_id") == FAKE_JOB_ID
    sub_manifest = index_changes_mock.call_args.args[1]
    assert sub_manifest.head_sha == "HEAD"
    assert sub_manifest.base_sha is None
    assert [c.path for c in sub_manifest.changes] == ["x.py", "y.py"]


def test_index_shard_honours_cancellation(fake_redis):
    repo = _make_repo()
    job = _make_job(state="embedding")
    payload = [
        {"path": f"f{i}.py", "blob_sha": "s", "change": "added", "size": 1}
        for i in range(5)
    ]

    # Cancel mid-shard: not cancelled at start, then flips True so the per-file
    # loop short-circuits before we ever call index_changes.
    flips = iter([False, True])

    def _cancel(_job_id):
        try:
            return next(flips)
        except StopIteration:
            return True

    index_changes_mock = AsyncMock()

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.index_changes",
            new=index_changes_mock,
        ),
        patch(
            "app.services.index_progress.is_cancelled_sync",
            side_effect=_cancel,
        ),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run_shard(FAKE_JOB_ID, payload)
        )

    # All files were dropped by cancellation → shard returns the empty marker.
    assert result["cancelled"] is True
    assert result["shard_size"] == 0
    index_changes_mock.assert_not_called()


# ── finalize_index_job ──────────────────────────────────────────────────────


def test_finalize_index_job_aggregates_and_marks_done(fake_redis):
    repo = _make_repo()
    job = _make_job(state="embedding")

    shard_results = [
        {
            "indexed": True, "added": 2, "modified": 1, "deleted": 0,
            "chunks_done": 10, "files_failed": 0, "shard_size": 3,
            "cancelled": False,
        },
        {
            "indexed": True, "added": 1, "modified": 0, "deleted": 0,
            "chunks_done": 4, "files_failed": 1, "shard_size": 2,
            "cancelled": False,
        },
        {
            "indexed": True, "added": 0, "modified": 2, "deleted": 1,
            "chunks_done": 6, "files_failed": 0, "shard_size": 3,
            "cancelled": False,
        },
    ]

    finalize_repo_mock = AsyncMock(
        return_value={"file_count": 3, "chunk_count": 20, "last_commit_sha": "HEAD"}
    )

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.finalize_repo",
            new=finalize_repo_mock,
        ),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run_finalize(shard_results, FAKE_JOB_ID)
        )

    finalize_repo_mock.assert_awaited_once()
    assert result["finalized"] is True
    assert result["state"] == "done"
    assert result["totals"]["added"] == 3
    assert result["totals"]["modified"] == 3
    assert result["totals"]["deleted"] == 1
    assert result["totals"]["chunks_done"] == 20
    assert job.state == "done"
    assert job.counters.files_added == 3
    assert job.counters.files_modified == 3
    assert job.counters.files_deleted == 1
    assert job.shards_done == 3


def test_finalize_index_job_marks_cancelled_when_any_shard_cancelled(fake_redis):
    repo = _make_repo()
    job = _make_job(state="embedding")

    shard_results = [
        {
            "indexed": True, "added": 1, "modified": 0, "deleted": 0,
            "chunks_done": 1, "files_failed": 0, "shard_size": 1,
            "cancelled": True,
        },
    ]

    with (
        patch("app.db.init_db", new=AsyncMock()),
        patch(
            "app.models.index_job.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "app.models.code_repository.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.services.code_repository_manager.code_repository_manager.finalize_repo",
            new=AsyncMock(return_value={}),
        ),
    ):
        asyncio.new_event_loop().run_until_complete(
            task_mod._run_finalize(shard_results, FAKE_JOB_ID)
        )

    assert job.state == "cancelled"
