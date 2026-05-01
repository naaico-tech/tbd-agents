"""Tests for the CodeRepository model, manager, and API."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main import app as _app
from app.models.code_repository import (
    CodeRepository,
    CodeRepositoryStatus,
)
from app.services.code_repository_manager import CodeRepositoryManager

FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_ID_2 = "6601a1b2c3d4e5f607890abd"


# ── Auth override ────────────────────────────────────────────────────────────


def _user_dep(login: str = "testuser"):
    def _dep():
        return {"login": login, "id": 1, "name": "Test User"}

    return _dep


@pytest.fixture(autouse=True)
def override_auth():
    _app.dependency_overrides[get_current_user] = _user_dep("testuser")
    yield
    _app.dependency_overrides.pop(get_current_user, None)


# ── Model + enum tests ───────────────────────────────────────────────────────


def test_status_enum_values():
    assert CodeRepositoryStatus.REGISTERED == "registered"
    assert CodeRepositoryStatus.SYNCING == "syncing"
    assert CodeRepositoryStatus.SYNCED == "synced"
    assert CodeRepositoryStatus.INDEXING == "indexing"
    assert CodeRepositoryStatus.INDEXED == "indexed"
    assert CodeRepositoryStatus.ERROR == "error"


def test_code_repository_model_defaults():
    repo = CodeRepository.model_construct(
        name="r", repo_url="https://github.com/x/y"
    )
    fields = CodeRepository.model_fields
    assert fields["status"].default == CodeRepositoryStatus.REGISTERED
    assert fields["file_count"].default == 0
    assert fields["gitnexus_job_id"].default is None
    assert fields["default_branch"].default == "main"
    assert repo.repo_url == "https://github.com/x/y"


# ── Manager unit tests ───────────────────────────────────────────────────────


def _fake_repo(
    repo_id: str = FAKE_ID,
    name: str = "r1",
    tags: list[str] | None = None,
    gitnexus_job_id: str | None = None,
):
    """A duck-typed CodeRepository sufficient for manager unit tests."""
    return SimpleNamespace(
        id=repo_id,
        name=name,
        description="",
        repo_url="https://github.com/x/y",
        default_branch="main",
        token_name=None,
        tags=tags or [],
        status=CodeRepositoryStatus.REGISTERED,
        last_synced_at=None,
        last_indexed_at=None,
        last_commit_sha=None,
        last_error=None,
        local_path=None,
        gitnexus_job_id=gitnexus_job_id,
        file_count=0,
        github_user="testuser",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_manager_sync_returns_none_for_empty_url():
    mgr = CodeRepositoryManager()
    repo = _fake_repo()
    repo.repo_url = ""
    assert await mgr.sync(repo) is None


@pytest.mark.asyncio
async def test_manager_sync_clones(tmp_path, monkeypatch):
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "repos_base", str(tmp_path))

    mgr = CodeRepositoryManager()
    repo = _fake_repo()

    proc = AsyncMock()
    proc.returncode = 0
    proc.communicate = AsyncMock(return_value=(b"abc123\n", b""))

    with patch(
        "app.services.code_repository_manager.asyncio.create_subprocess_shell",
        new=AsyncMock(return_value=proc),
    ):
        result = await mgr.sync(repo, force=True)

    assert result is not None
    assert repo.status == CodeRepositoryStatus.SYNCED
    assert repo.last_commit_sha == "abc123"


@pytest.mark.asyncio
async def test_manager_sync_failure_sets_error(tmp_path, monkeypatch):
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "repos_base", str(tmp_path))
    mgr = CodeRepositoryManager()
    repo = _fake_repo()

    proc = AsyncMock()
    proc.returncode = 128
    proc.communicate = AsyncMock(return_value=(b"", b"fatal: nope"))

    with patch(
        "app.services.code_repository_manager.asyncio.create_subprocess_shell",
        new=AsyncMock(return_value=proc),
    ):
        result = await mgr.sync(repo, force=True)

    assert result is None
    assert repo.status == CodeRepositoryStatus.ERROR
    assert "fatal" in (repo.last_error or "")


@pytest.mark.asyncio
async def test_manager_sync_ttl_cache_skips_clone(tmp_path):
    mgr = CodeRepositoryManager()
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    repo = _fake_repo()
    repo.local_path = str(tmp_path)
    repo.last_synced_at = datetime.now(UTC)

    # Should NOT call subprocess
    with patch(
        "app.services.code_repository_manager.asyncio.create_subprocess_shell",
        new=AsyncMock(side_effect=AssertionError("should not run")),
    ):
        result = await mgr.sync(repo, force=False)

    assert result == str(tmp_path)


@pytest.mark.asyncio
async def test_manager_search_always_returns_empty():
    """search() is stubbed — real search goes through GitNexus MCP."""
    mgr = CodeRepositoryManager()
    assert await mgr.search([], "anything") == []
    assert await mgr.search([_fake_repo()], "anything") == []


@pytest.mark.asyncio
async def test_manager_index_not_synced():
    mgr = CodeRepositoryManager()
    repo = _fake_repo()
    result = await mgr.index(repo)
    assert result["indexed"] is False
    assert result["reason"] == "not_synced"


@pytest.mark.asyncio
async def test_manager_index_no_gitnexus_url(tmp_path, monkeypatch):
    """When gitnexus_url is unset the compat shim falls back to the embedding pipeline."""
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "gitnexus_url", None)
    mgr = CodeRepositoryManager()
    repo = _fake_repo()
    repo.local_path = str(tmp_path)
    repo.last_commit_sha = "abc123"  # short-circuits rev-parse

    from app.services.code_repository_manager import Manifest

    fake_manifest = Manifest(head_sha="abc123", base_sha=None, changes=[])

    with (
        patch(
            "app.services.code_repository_manager.discover_changes",
            new=AsyncMock(return_value=fake_manifest),
        ),
        patch.object(
            mgr,
            "index_changes",
            new=AsyncMock(return_value={"indexed": True, "file_count": 0, "chunk_count": 0}),
        ),
    ):
        result = await mgr.index(repo)

    assert result["indexed"] is True
    assert "file_count" in result


@pytest.mark.asyncio
async def test_manager_index_triggers_gitnexus(tmp_path, monkeypatch):
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "gitnexus_url", "http://gitnexus:4747")
    mgr = CodeRepositoryManager()
    repo = _fake_repo()
    repo.local_path = str(tmp_path)

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"jobId": "job-abc", "status": "queued"})

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.post = AsyncMock(return_value=fake_resp)

    with patch("app.services.code_repository_manager.httpx.AsyncClient", return_value=fake_client):
        result = await mgr.index(repo)

    assert result["indexed"] is True
    assert result["gitnexus_job_id"] == "job-abc"
    assert repo.status == CodeRepositoryStatus.INDEXING
    assert repo.gitnexus_job_id == "job-abc"
    fake_client.post.assert_awaited_once()
    call_kwargs = fake_client.post.call_args
    assert "/api/analyze" in call_kwargs[0][0]


@pytest.mark.asyncio
async def test_manager_check_index_status_complete(monkeypatch):
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "gitnexus_url", "http://gitnexus:4747")
    mgr = CodeRepositoryManager()
    repo = _fake_repo(gitnexus_job_id="job-xyz")
    repo.status = CodeRepositoryStatus.INDEXING

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"status": "complete"})

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.get = AsyncMock(return_value=fake_resp)

    with patch("app.services.code_repository_manager.httpx.AsyncClient", return_value=fake_client):
        result = await mgr.check_index_status(repo)

    assert result["gitnexus_status"] == "complete"
    assert repo.status == CodeRepositoryStatus.INDEXED
    assert repo.gitnexus_job_id is None


@pytest.mark.asyncio
async def test_manager_check_index_status_failed(monkeypatch):
    from app.services import code_repository_manager as mod

    monkeypatch.setattr(mod.settings, "gitnexus_url", "http://gitnexus:4747")
    mgr = CodeRepositoryManager()
    repo = _fake_repo(gitnexus_job_id="job-fail")
    repo.status = CodeRepositoryStatus.INDEXING

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json = MagicMock(return_value={"status": "failed", "error": "boom"})

    fake_client = AsyncMock()
    fake_client.__aenter__ = AsyncMock(return_value=fake_client)
    fake_client.__aexit__ = AsyncMock(return_value=False)
    fake_client.get = AsyncMock(return_value=fake_resp)

    with patch("app.services.code_repository_manager.httpx.AsyncClient", return_value=fake_client):
        result = await mgr.check_index_status(repo)

    assert result["gitnexus_status"] == "failed"
    assert repo.status == CodeRepositoryStatus.ERROR
    assert "boom" in (repo.last_error or "")


@pytest.mark.asyncio
async def test_resolve_for_workflow_dedupes_id_and_tag():
    """Same repo referenced by id AND tag should appear once."""
    mgr = CodeRepositoryManager()
    repo1 = _fake_repo(repo_id=FAKE_ID, name="r1", tags=["billing"])
    repo2 = _fake_repo(repo_id=FAKE_ID_2, name="r2", tags=["billing"])

    workflow = SimpleNamespace(
        repository_ids=[FAKE_ID],
        repository_tags=["billing"],
    )

    fake_get = AsyncMock(return_value=repo1)
    fake_find = MagicMock()
    fake_find.return_value.to_list = AsyncMock(return_value=[repo1, repo2])

    with (
        patch.object(CodeRepository, "get", fake_get),
        patch.object(CodeRepository, "find", fake_find),
    ):
        result = await mgr.resolve_for_workflow(workflow)

    ids = sorted(str(r.id) for r in result)
    assert ids == sorted([FAKE_ID, FAKE_ID_2])


@pytest.mark.asyncio
async def test_resolve_for_workflow_empty_returns_empty():
    mgr = CodeRepositoryManager()
    workflow = SimpleNamespace(repository_ids=[], repository_tags=[])
    assert await mgr.resolve_for_workflow(workflow) == []


# ── API route tests ──────────────────────────────────────────────────────────


def _route_repo(repo_id: str = FAKE_ID, github_user: str = "testuser"):
    repo = SimpleNamespace(
        id=repo_id,
        name="My Repo",
        description="desc",
        repo_url="https://github.com/x/y",
        default_branch="main",
        token_name=None,
        tags=["t1"],
        status=CodeRepositoryStatus.REGISTERED,
        last_synced_at=None,
        last_indexed_at=None,
        last_commit_sha=None,
        last_error=None,
        local_path=None,
        gitnexus_job_id=None,
        file_count=0,
        github_user=github_user,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    repo.save = AsyncMock()
    repo.delete = AsyncMock()
    return repo


def test_create_code_repository(app_client):
    inserted = MagicMock()
    inserted.id = FAKE_ID
    inserted.name = "My Repo"
    inserted.description = ""
    inserted.repo_url = "https://github.com/x/y"
    inserted.default_branch = "main"
    inserted.token_name = None
    inserted.tags = ["t1"]
    inserted.status = CodeRepositoryStatus.REGISTERED
    inserted.last_synced_at = None
    inserted.last_indexed_at = None
    inserted.last_commit_sha = None
    inserted.last_error = None
    inserted.local_path = None
    inserted.gitnexus_job_id = None
    inserted.file_count = 0
    inserted.github_user = "testuser"
    inserted.created_at = datetime.now(UTC)
    inserted.updated_at = datetime.now(UTC)
    inserted.insert = AsyncMock()

    with patch(
        "app.api.routes.code_repositories.CodeRepository",
        return_value=inserted,
    ):
        resp = app_client.post(
            "/api/code-repositories",
            json={
                "name": "My Repo",
                "repo_url": "https://github.com/x/y",
                "tags": ["t1"],
            },
        )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "My Repo"
    assert body["github_user"] == "testuser"
    assert body["tags"] == ["t1"]


def test_list_code_repositories(app_client):
    repos = [_route_repo()]
    fake_find_all = MagicMock()
    fake_find_all.return_value.to_list = AsyncMock(return_value=repos)

    with patch.object(CodeRepository, "find_all", fake_find_all):
        resp = app_client.get("/api/code-repositories")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "My Repo"


def test_list_code_repositories_filter_by_tags(app_client):
    repos = [_route_repo()]
    fake_find = MagicMock()
    fake_find.return_value.to_list = AsyncMock(return_value=repos)

    with patch.object(CodeRepository, "find", fake_find):
        resp = app_client.get("/api/code-repositories?tags=t1,t2")
    assert resp.status_code == 200
    fake_find.assert_called_once()
    # The query should be {"tags": {"$in": [...]}}
    call_args = fake_find.call_args[0][0]
    assert call_args == {"tags": {"$in": ["t1", "t2"]}}


def test_get_code_repository_404(app_client):
    with patch.object(CodeRepository, "get", AsyncMock(return_value=None)):
        resp = app_client.get(f"/api/code-repositories/{FAKE_ID}")
    assert resp.status_code == 404


def test_get_code_repository_ok(app_client):
    repo = _route_repo()
    with patch.object(CodeRepository, "get", AsyncMock(return_value=repo)):
        resp = app_client.get(f"/api/code-repositories/{FAKE_ID}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Repo"


def test_update_code_repository_owner_check(app_client):
    repo = _route_repo(github_user="someone-else")
    with patch.object(CodeRepository, "get", AsyncMock(return_value=repo)):
        resp = app_client.put(
            f"/api/code-repositories/{FAKE_ID}",
            json={"name": "New Name"},
        )
    assert resp.status_code == 403


def test_update_code_repository_ok(app_client):
    repo = _route_repo()
    with patch.object(CodeRepository, "get", AsyncMock(return_value=repo)):
        resp = app_client.put(
            f"/api/code-repositories/{FAKE_ID}",
            json={"name": "Renamed", "tags": ["new"]},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["tags"] == ["new"]


def test_delete_code_repository_owner_check(app_client):
    repo = _route_repo(github_user="someone-else")
    with patch.object(CodeRepository, "get", AsyncMock(return_value=repo)):
        resp = app_client.delete(f"/api/code-repositories/{FAKE_ID}")
    assert resp.status_code == 403


def test_delete_code_repository_ok(app_client):
    repo = _route_repo()
    with (
        patch.object(CodeRepository, "get", AsyncMock(return_value=repo)),
        patch(
            "app.api.routes.code_repositories.code_repository_manager.delete",
            new=AsyncMock(),
        ),
    ):
        resp = app_client.delete(f"/api/code-repositories/{FAKE_ID}")
    assert resp.status_code == 204
    repo.delete.assert_awaited()


def test_sync_code_repository_owner_check(app_client):
    repo = _route_repo(github_user="someone-else")
    with patch.object(CodeRepository, "get", AsyncMock(return_value=repo)):
        resp = app_client.post(f"/api/code-repositories/{FAKE_ID}/sync")
    assert resp.status_code == 403


def test_sync_code_repository_ok(app_client):
    repo = _route_repo()

    async def _do_sync(self_repo, force=False):
        self_repo.status = CodeRepositoryStatus.SYNCED
        self_repo.local_path = "/tmp/x"
        self_repo.last_commit_sha = "abc"

    with (
        patch.object(CodeRepository, "get", AsyncMock(return_value=repo)),
        patch(
            "app.api.routes.code_repositories.code_repository_manager.sync",
            new=AsyncMock(side_effect=_do_sync),
        ),
    ):
        resp = app_client.post(f"/api/code-repositories/{FAKE_ID}/sync")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "synced"
    assert body["local_path"] == "/tmp/x"


def test_index_code_repository_ok(app_client):
    repo = _route_repo()
    repo.local_path = "/repos/abc123"

    inserted = MagicMock()
    inserted.id = FAKE_ID
    inserted.state = "queued"
    inserted.insert = AsyncMock(return_value=inserted)

    job_cls = MagicMock(return_value=inserted)
    job_cls.find_one = AsyncMock(return_value=None)
    delay_mock = MagicMock()

    with (
        patch.object(CodeRepository, "get", AsyncMock(return_value=repo)),
        patch("app.api.routes.code_repositories.IndexJob", new=job_cls),
        patch(
            "app.tasks.index_repository_task.run_index_repository_job.delay",
            delay_mock,
        ),
        patch("app.api.routes.code_repositories.settings") as mock_settings,
    ):
        mock_settings.gitnexus_url = None
        resp = app_client.post(f"/api/code-repositories/{FAKE_ID}/index")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["job_id"] == FAKE_ID
    assert body["state"] == "queued"
    assert body["idempotent"] is False


def test_index_status_route_polling(app_client):
    repo = _route_repo()
    repo.status = CodeRepositoryStatus.INDEXING
    repo.gitnexus_job_id = "job-42"

    async def _do_check(r):
        r.status = CodeRepositoryStatus.INDEXED
        r.gitnexus_job_id = None
        return {"status": CodeRepositoryStatus.INDEXED, "gitnexus_status": "complete"}

    with (
        patch.object(CodeRepository, "get", AsyncMock(return_value=repo)),
        patch(
            "app.api.routes.code_repositories.code_repository_manager.check_index_status",
            new=AsyncMock(side_effect=_do_check),
        ),
    ):
        resp = app_client.get(f"/api/code-repositories/{FAKE_ID}/index/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "indexed"
    assert body["indexed"] is True
    assert body["gitnexus_job_id"] is None


def test_export_all_code_repositories(app_client):
    repos = [_route_repo()]
    fake_find_all = MagicMock()
    fake_find_all.return_value.to_list = AsyncMock(return_value=repos)
    with patch.object(CodeRepository, "find_all", fake_find_all):
        resp = app_client.get("/api/code-repositories/export")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "My Repo"


def test_import_code_repositories(app_client):
    inserted = MagicMock()
    inserted.id = FAKE_ID
    inserted.insert = AsyncMock()

    with patch(
        "app.api.routes.code_repositories.CodeRepository",
        return_value=inserted,
    ):
        resp = app_client.post(
            "/api/code-repositories/import",
            json={
                "items": [
                    {
                        "name": "Imported",
                        "repo_url": "https://github.com/x/z",
                        "tags": ["tg"],
                    }
                ]
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["created"] == 1
    inserted.insert.assert_awaited()


# ── Workflow integration ─────────────────────────────────────────────────────


def test_workflow_schemas_accept_repository_fields():
    from app.schemas.workflow import WorkflowCreate, WorkflowResponse, WorkflowUpdate

    create = WorkflowCreate(
        agent_id=FAKE_ID,
        prompt="hi",
        repository_ids=[FAKE_ID],
        repository_tags=["billing"],
    )
    assert create.repository_ids == [FAKE_ID]
    assert create.repository_tags == ["billing"]

    upd = WorkflowUpdate(repository_ids=[FAKE_ID_2])
    assert upd.repository_ids == [FAKE_ID_2]

    fields = WorkflowResponse.model_fields
    assert "repository_ids" in fields
    assert "repository_tags" in fields


def test_exported_workflow_has_repository_fields():
    from app.schemas.export_import import ExportedWorkflow

    fields = ExportedWorkflow.model_fields
    assert "repository_ids" in fields
    assert "repository_tags" in fields
