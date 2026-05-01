"""Tests for the IndexJob async indexing envelope (PR1)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest

from app.api.deps import get_current_user
from app.main import app as _app
from app.models.code_repository import CodeRepositoryStatus, IndexingConfig
from app.models.index_job import (
    TERMINAL_STATES,
    IndexJob,
    IndexJobCounters,
    IndexJobError,
)

FAKE_REPO_ID = "6601a1b2c3d4e5f607890abc"
FAKE_JOB_ID = "6601a1b2c3d4e5f607890def"
FAKE_JOB_ID_2 = "6601a1b2c3d4e5f607890e00"


# ── Auth override ──────────────────────────────────────────────────────────


def _user_dep():
    def _dep():
        return {"login": "testuser", "id": 1, "name": "Test User"}

    return _dep


@pytest.fixture(autouse=True)
def override_auth():
    _app.dependency_overrides[get_current_user] = _user_dep()
    yield
    _app.dependency_overrides.pop(get_current_user, None)


# ── Fake redis (replaces module-level _redis() factory) ────────────────────


@pytest.fixture()
def fake_redis(monkeypatch):
    from app.services import index_progress as ip

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(ip, "_redis", lambda: client)
    yield client


# ── Helpers ────────────────────────────────────────────────────────────────


def _route_repo(repo_id: str = FAKE_REPO_ID, github_user: str = "testuser"):
    repo = SimpleNamespace(
        id=repo_id,
        name="My Repo",
        description="d",
        repo_url="https://github.com/x/y",
        default_branch="main",
        token_name=None,
        tags=[],
        status=CodeRepositoryStatus.REGISTERED,
        last_synced_at=None,
        last_indexed_at=None,
        last_commit_sha=None,
        last_error=None,
        local_path=None,
        indexing=IndexingConfig(),
        vector_collection=None,
        file_count=0,
        chunk_count=0,
        last_indexed_job_id=None,
        github_user=github_user,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save = AsyncMock()
    return repo


def _make_job(
    job_id: str = FAKE_JOB_ID,
    repo_id: str = FAKE_REPO_ID,
    state: str = "queued",
    current_phase: str = "queued",
    current_file: str | None = None,
    counters: IndexJobCounters | None = None,
    error: IndexJobError | None = None,
):
    """Lightweight stand-in for an IndexJob doc — duck-typed for the route."""
    job = SimpleNamespace(
        id=job_id,
        repo_id=repo_id,
        kind="full",
        state=state,
        current_phase=current_phase,
        current_file=current_file,
        counters=counters or IndexJobCounters(),
        head_commit_sha=None,
        base_commit_sha=None,
        started_at=None,
        finished_at=None,
        eta_seconds=None,
        error=error,
        shard_count=1,
        shards_done=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    job.save = AsyncMock()
    job.insert = AsyncMock()
    return job


# ── Model defaults ─────────────────────────────────────────────────────────


def test_index_job_counters_defaults():
    c = IndexJobCounters()
    assert c.files_total == 0
    assert c.chunks_done == 0
    assert c.bytes_done == 0


def test_index_job_terminal_states():
    assert TERMINAL_STATES == {"done", "failed", "cancelled"}


def test_index_job_default_state():
    fields = IndexJob.model_fields
    assert fields["state"].default == "queued"
    assert fields["kind"].default == "full"
    assert fields["shard_count"].default == 1


# ── POST /index — enqueue + idempotency ────────────────────────────────────


def test_post_index_enqueues_job(app_client):
    repo = _route_repo()
    inserted = _make_job(job_id=FAKE_JOB_ID)

    delay_mock = MagicMock()

    job_cls = MagicMock(return_value=inserted)
    job_cls.find_one = AsyncMock(return_value=None)

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch("app.api.routes.code_repositories.IndexJob", new=job_cls),
        patch(
            "app.tasks.index_repository_task.run_index_repository_job.delay",
            delay_mock,
        ),
        patch("app.api.routes.code_repositories.settings") as mock_settings,
    ):
        mock_settings.gitnexus_url = None
        resp = app_client.post(f"/api/code-repositories/{FAKE_REPO_ID}/index")

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == FAKE_JOB_ID
    assert body["state"] == "queued"
    assert body["idempotent"] is False
    delay_mock.assert_called_once_with(FAKE_JOB_ID, False)


def test_post_index_is_idempotent(app_client):
    repo = _route_repo()
    existing = _make_job(job_id=FAKE_JOB_ID, state="embedding")
    delay_mock = MagicMock()

    job_cls = MagicMock()
    job_cls.find_one = AsyncMock(return_value=existing)

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch("app.api.routes.code_repositories.IndexJob", new=job_cls),
        patch(
            "app.tasks.index_repository_task.run_index_repository_job.delay",
            delay_mock,
        ),
        patch("app.api.routes.code_repositories.settings") as mock_settings,
    ):
        mock_settings.gitnexus_url = None
        resp = app_client.post(f"/api/code-repositories/{FAKE_REPO_ID}/index")

    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == FAKE_JOB_ID
    assert body["idempotent"] is True
    assert body["state"] == "embedding"
    delay_mock.assert_not_called()


def test_post_index_force_passes_flag(app_client):
    """?force=true must pass force_full=True to the Celery task."""
    repo = _route_repo()
    inserted = _make_job(job_id=FAKE_JOB_ID)

    delay_mock = MagicMock()
    job_cls = MagicMock(return_value=inserted)
    job_cls.find_one = AsyncMock(return_value=None)

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch("app.api.routes.code_repositories.IndexJob", new=job_cls),
        patch(
            "app.tasks.index_repository_task.run_index_repository_job.delay",
            delay_mock,
        ),
        patch("app.api.routes.code_repositories.settings") as mock_settings,
    ):
        mock_settings.gitnexus_url = None
        resp = app_client.post(
            f"/api/code-repositories/{FAKE_REPO_ID}/index?force=true"
        )

    assert resp.status_code == 202, resp.text
    delay_mock.assert_called_once_with(FAKE_JOB_ID, True)


def test_post_index_owner_check(app_client):
    repo = _route_repo(github_user="someone-else")
    with patch(
        "app.api.routes.code_repositories.CodeRepository.get",
        new=AsyncMock(return_value=repo),
    ):
        resp = app_client.post(f"/api/code-repositories/{FAKE_REPO_ID}/index")
    assert resp.status_code == 403


# ── GET /jobs ──────────────────────────────────────────────────────────────


def test_list_jobs(app_client):
    repo = _route_repo()
    j1 = _make_job(job_id=FAKE_JOB_ID, state="done")
    j2 = _make_job(job_id=FAKE_JOB_ID_2, state="queued")

    fake_query = MagicMock()
    fake_query.sort.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[j2, j1]
    )
    job_cls = MagicMock()
    job_cls.find.return_value = fake_query
    job_cls.created_at = MagicMock()  # needed for `-IndexJob.created_at`

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch("app.api.routes.code_repositories.IndexJob", new=job_cls),
    ):
        resp = app_client.get(f"/api/code-repositories/{FAKE_REPO_ID}/jobs")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == FAKE_JOB_ID_2
    assert body[1]["id"] == FAKE_JOB_ID


# ── GET /jobs/{id} — Redis overlay merge ──────────────────────────────────


def test_get_job_merges_redis_overlay(app_client, fake_redis):
    """Mongo says queued/0 chunks; Redis says embedding/42 chunks → Redis wins."""
    import asyncio

    from app.services import index_progress

    async def _seed():
        await index_progress.init_progress(
            FAKE_JOB_ID, files_total=10, chunks_total=100
        )
        await index_progress.set_phase(
            FAKE_JOB_ID, "embedding", current_file="src/main.py"
        )
        await index_progress.incr(FAKE_JOB_ID, files_done=3, chunks_done=42)

    asyncio.new_event_loop().run_until_complete(_seed())

    repo = _route_repo()
    job = _make_job(
        job_id=FAKE_JOB_ID,
        state="embedding",
        current_phase="discovering",
        counters=IndexJobCounters(
            files_total=10, chunks_total=100, chunks_done=0
        ),
    )

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.api.routes.code_repositories.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
    ):
        resp = app_client.get(
            f"/api/code-repositories/{FAKE_REPO_ID}/jobs/{FAKE_JOB_ID}"
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Redis overlay wins on counters / phase / current_file.
    assert body["counters"]["chunks_done"] == 42
    assert body["counters"]["files_done"] == 3
    assert body["current_phase"] == "embedding"
    assert body["current_file"] == "src/main.py"
    # progress_pct computed from Redis counters
    assert body["progress_pct"] == 42.0
    assert body["is_terminal"] is False


# ── Cancel ────────────────────────────────────────────────────────────────


def test_cancel_sets_redis_flag(app_client, fake_redis):
    import asyncio

    from app.services import index_progress

    repo = _route_repo()
    job = _make_job(job_id=FAKE_JOB_ID, state="embedding")

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.api.routes.code_repositories.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
    ):
        resp = app_client.post(
            f"/api/code-repositories/{FAKE_REPO_ID}/jobs/{FAKE_JOB_ID}/cancel"
        )

    assert resp.status_code == 200
    flagged = asyncio.new_event_loop().run_until_complete(
        index_progress.is_cancelled(FAKE_JOB_ID)
    )
    assert flagged is True


def test_cancel_terminal_job_noops(app_client, fake_redis):
    import asyncio

    from app.services import index_progress

    repo = _route_repo()
    job = _make_job(job_id=FAKE_JOB_ID, state="done")

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.api.routes.code_repositories.IndexJob.get",
            new=AsyncMock(return_value=job),
        ),
    ):
        resp = app_client.post(
            f"/api/code-repositories/{FAKE_REPO_ID}/jobs/{FAKE_JOB_ID}/cancel"
        )

    assert resp.status_code == 200
    flagged = asyncio.new_event_loop().run_until_complete(
        index_progress.is_cancelled(FAKE_JOB_ID)
    )
    assert flagged is False


# ── SSE ───────────────────────────────────────────────────────────────────


def test_sse_emits_progress_event(app_client, fake_redis):
    """Verify content-type and that at least one progress event arrives."""
    import asyncio

    from app.services import index_progress

    repo = _route_repo()
    # Use a state that flips to terminal so the stream closes quickly.
    states = iter([
        _make_job(
            job_id=FAKE_JOB_ID,
            state="embedding",
            current_phase="embedding",
            counters=IndexJobCounters(chunks_total=10, chunks_done=5),
        ),
        _make_job(
            job_id=FAKE_JOB_ID,
            state="done",
            current_phase="done",
            counters=IndexJobCounters(chunks_total=10, chunks_done=10),
        ),
    ])

    async def _get(_oid):
        try:
            return next(states)
        except StopIteration:
            return _make_job(
                job_id=FAKE_JOB_ID,
                state="done",
                current_phase="done",
                counters=IndexJobCounters(chunks_total=10, chunks_done=10),
            )

    asyncio.new_event_loop().run_until_complete(
        index_progress.init_progress(
            FAKE_JOB_ID, files_total=1, chunks_total=10
        )
    )
    asyncio.new_event_loop().run_until_complete(
        index_progress.incr(FAKE_JOB_ID, chunks_done=5)
    )

    with (
        patch(
            "app.api.routes.code_repositories.CodeRepository.get",
            new=AsyncMock(return_value=repo),
        ),
        patch(
            "app.api.routes.code_repositories.IndexJob.get",
            new=AsyncMock(side_effect=_get),
        ),
    ):
        with app_client.stream(
            "GET",
            f"/api/code-repositories/{FAKE_REPO_ID}/jobs/{FAKE_JOB_ID}/events",
        ) as r:
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/event-stream")
            chunks: list[str] = []
            for line in r.iter_lines():
                chunks.append(line)
                # Stop once we've seen at least one progress event + terminator.
                if any("event: done" in c for c in chunks):
                    break

    blob = "\n".join(chunks)
    assert "event: progress" in blob
    assert "event: done" in blob


# ── Celery task body: base/head sha population (PR2) ────────────────────────


def test_run_indexes_populates_base_and_head_sha(fake_redis):
    """Driving the task body in-process must persist base→head sha pair on the
    IndexJob and pick ``kind='incremental'`` when the manifest had a base.
    The orchestrator now launches a chord rather than indexing inline, so we
    only assert the pre-chord state transitions and that the chord was kicked.
    """
    import asyncio

    from app.models.code_repository import CodeRepositoryStatus
    from app.services.code_repository_manager import FileChange, Manifest
    from app.tasks import index_repository_task as task_mod

    job = _make_job(state="queued", current_phase="queued")
    job.base_commit_sha = None
    job.head_commit_sha = None
    job.kind = "full"

    repo = _route_repo()
    repo.last_commit_sha = "BASE_SHA"  # snapshot before sync()
    repo.local_path = "/tmp/repo"

    async def _fake_sync(_repo, force=False):  # noqa: ARG001
        # sync() overwrites last_commit_sha to the new HEAD.
        _repo.last_commit_sha = "HEAD_SHA"
        _repo.status = CodeRepositoryStatus.SYNCED
        return _repo.local_path

    fake_manifest = Manifest(
        head_sha="HEAD_SHA",
        base_sha="BASE_SHA",
        changes=[FileChange(path="x.py", blob_sha="sx", change="modified", size=1)],
    )

    chord_mock = MagicMock()
    chord_mock.return_value.apply_async.return_value = SimpleNamespace(
        id="CHORD-XYZ"
    )

    with (
        patch("app.tasks.index_repository_task.init_db", new=AsyncMock())
        if hasattr(task_mod, "init_db")
        else patch("app.db.init_db", new=AsyncMock()),
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
            new=AsyncMock(side_effect=_fake_sync),
        ),
        patch(
            "app.services.code_repository_manager.discover_changes",
            new=AsyncMock(return_value=fake_manifest),
        ),
        patch("app.tasks.index_repository_task.chord", chord_mock),
    ):
        result = asyncio.new_event_loop().run_until_complete(
            task_mod._run(FAKE_JOB_ID, worker="test")
        )

    assert job.base_commit_sha == "BASE_SHA"
    assert job.head_commit_sha == "HEAD_SHA"
    assert job.kind == "incremental"
    # Orchestrator transitions to embedding before the chord fires; finalize
    # callback (not exercised here) would flip it to done.
    assert job.state == "embedding"
    assert result["chord_id"] == "CHORD-XYZ"
    assert result["shard_count"] >= 1
    chord_mock.return_value.apply_async.assert_called_once()


def test_run_indexes_marks_full_when_no_base(fake_redis):
    """First-time index → manifest.base_sha is None → kind='full'."""
    import asyncio

    from app.models.code_repository import CodeRepositoryStatus
    from app.services.code_repository_manager import FileChange, Manifest
    from app.tasks import index_repository_task as task_mod

    job = _make_job(state="queued", current_phase="queued")
    repo = _route_repo()
    repo.last_commit_sha = None  # no prior index
    repo.local_path = "/tmp/repo"

    async def _fake_sync(_repo, force=False):  # noqa: ARG001
        _repo.last_commit_sha = "HEAD_ONLY"
        _repo.status = CodeRepositoryStatus.SYNCED

    fake_manifest = Manifest(
        head_sha="HEAD_ONLY",
        base_sha=None,
        changes=[FileChange(path="a.py", blob_sha="sa", change="added", size=1)],
    )

    chord_mock = MagicMock()
    chord_mock.return_value.apply_async.return_value = SimpleNamespace(id="C")

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
            new=AsyncMock(side_effect=_fake_sync),
        ),
        patch(
            "app.services.code_repository_manager.discover_changes",
            new=AsyncMock(return_value=fake_manifest),
        ),
        patch("app.tasks.index_repository_task.chord", chord_mock),
    ):
        asyncio.new_event_loop().run_until_complete(
            task_mod._run(FAKE_JOB_ID, worker="test")
        )

    assert job.base_commit_sha is None
    assert job.head_commit_sha == "HEAD_ONLY"
    assert job.kind == "full"
    assert job.state == "embedding"
