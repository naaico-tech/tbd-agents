"""Tests for the /api/codegraph/* REST endpoints.

Auth pattern: FastAPI's Depends() captures ``get_current_user`` at import time,
so the correct override mechanism is ``app.dependency_overrides``.  The autouse
``override_auth`` fixture sets a "testuser" override for every test in this
module and tears it down afterwards.

Celery tasks are imported lazily inside route functions.  Because the ``celery``
package is not installed in the test environment we stub the entire
``app.tasks.codegraph_tasks`` module via ``patch.dict("sys.modules", ...)``.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main import app as _app
from app.models.codegraph_repo import CodeGraphRepoStatus

# ── Constants ─────────────────────────────────────────────────────────────────

FAKE_REPO_ID = "507f1f77bcf86cd799439011"
FAKE_REPO_ID_2 = "507f1f77bcf86cd799439012"
FAKE_MCP_ID = "507f1f77bcf86cd799439013"
FAKE_TASK_ID = "celery-task-abc-123"


# ── Auth override fixture ─────────────────────────────────────────────────────


def _make_user_override(login: str = "testuser"):
    """Return a dependency override callable that yields the given user dict."""

    def _dep():
        return {"login": login, "id": 1, "name": "Test User"}

    return _dep


@pytest.fixture(autouse=True)
def override_auth():
    """Override get_current_user for every test in this module."""
    _app.dependency_overrides[get_current_user] = _make_user_override("testuser")
    yield
    _app.dependency_overrides.pop(get_current_user, None)


# ── Fake model helpers ────────────────────────────────────────────────────────


def _fake_repo(
    repo_id: str = FAKE_REPO_ID,
    name: str = "test-repo",
    status: CodeGraphRepoStatus = CodeGraphRepoStatus.PENDING,
    mcp_server_id: str | None = None,
    local_path: str = "/opt/codegraph_repos/test-repo",
) -> MagicMock:
    """Return a MagicMock with all attributes required by ``_to_response``."""
    repo = MagicMock()
    repo.id = repo_id
    repo.name = name
    repo.repo_url = "https://github.com/test/repo"
    repo.local_path = local_path
    repo.status = status
    repo.indexed_at = None
    repo.error_message = None
    repo.agent_ids = []
    repo.mcp_server_id = mcp_server_id
    repo.celery_task_id = None
    repo.created_at = datetime.now(UTC)
    repo.updated_at = datetime.now(UTC)
    repo.save = AsyncMock()
    repo.delete = AsyncMock()
    repo.insert = AsyncMock()
    return repo


def _mock_celery_module(task_id: str = FAKE_TASK_ID) -> MagicMock:
    """Return a stub for ``app.tasks.codegraph_tasks`` with a ready ``index_repo_task``."""
    mock_task = MagicMock()
    mock_task.id = task_id
    mock_module = MagicMock()
    mock_module.index_repo_task.delay.return_value = mock_task
    return mock_module


# ── POST /api/codegraph/repos ─────────────────────────────────────────────────


class TestCreateRepo:
    """Tests for ``POST /api/codegraph/repos``."""

    def test_async_index_returns_202(self, app_client):
        """Returns 202 Accepted and dispatches a Celery task when async_index=True."""
        repo = _fake_repo()
        mock_celery = _mock_celery_module()

        mock_repo_cls = MagicMock(return_value=repo)
        mock_repo_cls.get = AsyncMock(return_value=repo)

        with (
            patch("app.api.routes.codegraph.CodeGraphRepo", mock_repo_cls),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            resp = app_client.post(
                "/api/codegraph/repos",
                json={
                    "name": "test-repo",
                    "repo_url": "https://github.com/test/repo",
                    "async_index": True,
                },
            )

        assert resp.status_code == 202
        data = resp.json()
        assert data["name"] == "test-repo"
        mock_celery.index_repo_task.delay.assert_called_once()

    def test_async_index_passes_correct_args_to_celery(self, app_client):
        """The Celery task is dispatched with (repo_id, repo_url, name)."""
        repo = _fake_repo()
        mock_celery = _mock_celery_module()

        mock_repo_cls = MagicMock(return_value=repo)
        mock_repo_cls.get = AsyncMock(return_value=repo)

        with (
            patch("app.api.routes.codegraph.CodeGraphRepo", mock_repo_cls),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            app_client.post(
                "/api/codegraph/repos",
                json={
                    "name": "test-repo",
                    "repo_url": "https://github.com/test/repo",
                    "async_index": True,
                },
            )

        call_args = mock_celery.index_repo_task.delay.call_args
        positional = call_args.args
        assert positional[0] == str(repo.id)  # repo_id
        assert positional[1] == "https://github.com/test/repo"  # repo_url
        assert positional[2] == "test-repo"  # name

    def test_sync_index_calls_service_directly(self, app_client):
        """When async_index=False, index_repository is awaited synchronously."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)
        mock_repo_cls = MagicMock(return_value=repo)
        mock_repo_cls.get = AsyncMock(return_value=repo)

        with (
            patch("app.api.routes.codegraph.CodeGraphRepo", mock_repo_cls),
            patch(
                "app.api.routes.codegraph.codegraph_service.index_repository",
                new_callable=AsyncMock,
            ) as mock_index,
        ):
            resp = app_client.post(
                "/api/codegraph/repos",
                json={
                    "name": "test-repo",
                    "repo_url": "https://github.com/test/repo",
                    "async_index": False,
                },
            )

        assert resp.status_code == 202
        mock_index.assert_awaited_once()

    def test_sync_index_does_not_call_celery(self, app_client):
        """When async_index=False, no Celery task is dispatched."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)
        mock_repo_cls = MagicMock(return_value=repo)
        mock_repo_cls.get = AsyncMock(return_value=repo)
        mock_celery = _mock_celery_module()

        with (
            patch("app.api.routes.codegraph.CodeGraphRepo", mock_repo_cls),
            patch(
                "app.api.routes.codegraph.codegraph_service.index_repository",
                new_callable=AsyncMock,
            ),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            app_client.post(
                "/api/codegraph/repos",
                json={
                    "name": "test-repo",
                    "repo_url": "https://github.com/test/repo",
                    "async_index": False,
                },
            )

        mock_celery.index_repo_task.delay.assert_not_called()

    def test_agent_ids_are_forwarded(self, app_client):
        """agent_ids from the request body are stored on the repo document."""
        captured_kwargs: dict = {}

        def _capture_ctor(**kwargs):
            captured_kwargs.update(kwargs)
            return _fake_repo()

        mock_repo_cls = MagicMock(side_effect=_capture_ctor)
        mock_repo_cls.get = AsyncMock(return_value=_fake_repo())
        mock_celery = _mock_celery_module()

        with (
            patch("app.api.routes.codegraph.CodeGraphRepo", mock_repo_cls),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            app_client.post(
                "/api/codegraph/repos",
                json={
                    "name": "test-repo",
                    "repo_url": "https://github.com/test/repo",
                    "agent_ids": ["agent-1", "agent-2"],
                    "async_index": True,
                },
            )

        assert captured_kwargs.get("agent_ids") == ["agent-1", "agent-2"]


# ── GET /api/codegraph/repos ──────────────────────────────────────────────────


class TestListRepos:
    """Tests for ``GET /api/codegraph/repos``."""

    def test_returns_list_of_repos(self, app_client):
        """Returns a JSON array containing all registered repositories."""
        repos = [
            _fake_repo(repo_id=FAKE_REPO_ID, name="repo-alpha"),
            _fake_repo(repo_id=FAKE_REPO_ID_2, name="repo-beta"),
        ]

        with patch(
            "app.api.routes.codegraph.codegraph_service.list_repositories",
            new_callable=AsyncMock,
            return_value=repos,
        ):
            resp = app_client.get("/api/codegraph/repos")

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert {r["name"] for r in data} == {"repo-alpha", "repo-beta"}

    def test_returns_empty_list_when_no_repos(self, app_client):
        """Returns an empty JSON array when no repositories are registered."""
        with patch(
            "app.api.routes.codegraph.codegraph_service.list_repositories",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = app_client.get("/api/codegraph/repos")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_response_shape_matches_schema(self, app_client):
        """Each repo object in the list contains all expected schema fields."""
        repos = [_fake_repo(repo_id=FAKE_REPO_ID, name="shape-check")]

        with patch(
            "app.api.routes.codegraph.codegraph_service.list_repositories",
            new_callable=AsyncMock,
            return_value=repos,
        ):
            resp = app_client.get("/api/codegraph/repos")

        assert resp.status_code == 200
        item = resp.json()[0]
        expected_keys = {
            "id", "name", "repo_url", "local_path", "status",
            "indexed_at", "error_message", "agent_ids",
            "mcp_server_id", "celery_task_id", "created_at", "updated_at",
        }
        assert expected_keys.issubset(item.keys())


# ── GET /api/codegraph/repos/{id} ─────────────────────────────────────────────


class TestGetRepo:
    """Tests for ``GET /api/codegraph/repos/{repo_id}``."""

    def test_returns_200_with_repo_details_when_found(self, app_client):
        """Returns 200 with the repository fields serialised as JSON."""
        repo = _fake_repo()

        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=repo,
        ):
            resp = app_client.get(f"/api/codegraph/repos/{FAKE_REPO_ID}")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == FAKE_REPO_ID
        assert data["name"] == "test-repo"
        assert data["repo_url"] == "https://github.com/test/repo"
        assert data["status"] == CodeGraphRepoStatus.PENDING

    def test_returns_404_when_repo_not_found(self, app_client):
        """Returns 404 Not Found when no document matches the given id."""
        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.get(f"/api/codegraph/repos/{FAKE_REPO_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CodeGraph repository not found"


# ── POST /api/codegraph/repos/{id}/reindex ───────────────────────────────────


class TestReindexRepo:
    """Tests for ``POST /api/codegraph/repos/{repo_id}/reindex``."""

    def test_returns_202_and_dispatches_celery_task(self, app_client):
        """Returns 202 Accepted and fires off a new Celery reindex task."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)
        mock_celery = _mock_celery_module()

        with (
            patch(
                "app.api.routes.codegraph.CodeGraphRepo.get",
                new_callable=AsyncMock,
                return_value=repo,
            ),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            resp = app_client.post(f"/api/codegraph/repos/{FAKE_REPO_ID}/reindex")

        assert resp.status_code == 202
        mock_celery.index_repo_task.delay.assert_called_once()

    def test_returns_404_when_repo_not_found(self, app_client):
        """Returns 404 Not Found when no document matches the given id."""
        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.post(f"/api/codegraph/repos/{FAKE_REPO_ID}/reindex")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CodeGraph repository not found"

    def test_reindex_sets_status_to_pending(self, app_client):
        """Repo status is reset to PENDING before the task is dispatched."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)
        mock_celery = _mock_celery_module()

        with (
            patch(
                "app.api.routes.codegraph.CodeGraphRepo.get",
                new_callable=AsyncMock,
                return_value=repo,
            ),
            patch.dict("sys.modules", {"app.tasks.codegraph_tasks": mock_celery}),
        ):
            resp = app_client.post(f"/api/codegraph/repos/{FAKE_REPO_ID}/reindex")

        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == CodeGraphRepoStatus.PENDING


# ── DELETE /api/codegraph/repos/{id} ─────────────────────────────────────────


class TestDeleteRepo:
    """Tests for ``DELETE /api/codegraph/repos/{repo_id}``."""

    def test_returns_204_on_success(self, app_client):
        """Returns 204 No Content when the repository is removed."""
        with patch(
            "app.api.routes.codegraph.codegraph_service.remove_repository",
            new_callable=AsyncMock,
        ) as mock_remove:
            resp = app_client.delete(f"/api/codegraph/repos/{FAKE_REPO_ID}")

        assert resp.status_code == 204
        mock_remove.assert_awaited_once_with(FAKE_REPO_ID, delete_local=False)

    def test_returns_404_when_service_raises_value_error(self, app_client):
        """Returns 404 Not Found when the service signals the repo is missing."""
        with patch(
            "app.api.routes.codegraph.codegraph_service.remove_repository",
            new_callable=AsyncMock,
            side_effect=ValueError("not found"),
        ):
            resp = app_client.delete(f"/api/codegraph/repos/{FAKE_REPO_ID}")

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CodeGraph repository not found"

    def test_passes_delete_local_true_query_param(self, app_client):
        """Forwards ``delete_local=True`` to the service when the QS flag is set."""
        with patch(
            "app.api.routes.codegraph.codegraph_service.remove_repository",
            new_callable=AsyncMock,
        ) as mock_remove:
            resp = app_client.delete(
                f"/api/codegraph/repos/{FAKE_REPO_ID}?delete_local=true"
            )

        assert resp.status_code == 204
        mock_remove.assert_awaited_once_with(FAKE_REPO_ID, delete_local=True)

    def test_delete_local_defaults_to_false(self, app_client):
        """delete_local defaults to False when the query parameter is omitted."""
        with patch(
            "app.api.routes.codegraph.codegraph_service.remove_repository",
            new_callable=AsyncMock,
        ) as mock_remove:
            app_client.delete(f"/api/codegraph/repos/{FAKE_REPO_ID}")

        _, kwargs = mock_remove.call_args
        assert kwargs.get("delete_local") is False


# ── POST /api/codegraph/repos/{id}/query ─────────────────────────────────────


class TestQueryRepo:
    """Tests for ``POST /api/codegraph/repos/{repo_id}/query``."""

    def test_returns_200_with_cli_output_when_ready(self, app_client):
        """Returns 200 and the parsed CLI dict when the repo is READY."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)
        expected = {"results": [{"file": "app/main.py", "line": 10}]}

        with (
            patch(
                "app.api.routes.codegraph.CodeGraphRepo.get",
                new_callable=AsyncMock,
                return_value=repo,
            ),
            patch(
                "app.api.routes.codegraph.codegraph_service.query_cli",
                new_callable=AsyncMock,
                return_value=expected,
            ),
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "search", "args": ["def main"]},
            )

        assert resp.status_code == 200
        assert resp.json() == expected

    def test_returns_409_when_repo_is_indexing(self, app_client):
        """Returns 409 Conflict when the repo status is INDEXING."""
        repo = _fake_repo(status=CodeGraphRepoStatus.INDEXING)

        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=repo,
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "search", "args": ["def main"]},
            )

        assert resp.status_code == 409
        assert "not ready" in resp.json()["detail"].lower()

    def test_returns_409_when_repo_is_pending(self, app_client):
        """Returns 409 Conflict when the repo status is PENDING."""
        repo = _fake_repo(status=CodeGraphRepoStatus.PENDING)

        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=repo,
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "callers", "args": []},
            )

        assert resp.status_code == 409

    def test_returns_409_when_repo_is_in_error_state(self, app_client):
        """Returns 409 Conflict when the repo status is ERROR."""
        repo = _fake_repo(status=CodeGraphRepoStatus.ERROR)

        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=repo,
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "search", "args": []},
            )

        assert resp.status_code == 409

    def test_returns_404_when_repo_not_found(self, app_client):
        """Returns 404 Not Found when no document matches the given id."""
        with patch(
            "app.api.routes.codegraph.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "search", "args": []},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"] == "CodeGraph repository not found"

    def test_returns_502_when_cli_raises_runtime_error(self, app_client):
        """Returns 502 Bad Gateway when query_cli raises RuntimeError."""
        repo = _fake_repo(status=CodeGraphRepoStatus.READY)

        with (
            patch(
                "app.api.routes.codegraph.CodeGraphRepo.get",
                new_callable=AsyncMock,
                return_value=repo,
            ),
            patch(
                "app.api.routes.codegraph.codegraph_service.query_cli",
                new_callable=AsyncMock,
                side_effect=RuntimeError("codegraph returned non-JSON output"),
            ),
        ):
            resp = app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "search", "args": []},
            )

        assert resp.status_code == 502
        assert "non-JSON" in resp.json()["detail"]

    def test_passes_command_and_args_to_service(self, app_client):
        """Forwards the command, args, and repo_id to codegraph_service.query_cli."""
        repo = _fake_repo(
            status=CodeGraphRepoStatus.READY,
            local_path="/opt/codegraph_repos/test-repo",
        )

        with (
            patch(
                "app.api.routes.codegraph.CodeGraphRepo.get",
                new_callable=AsyncMock,
                return_value=repo,
            ),
            patch(
                "app.api.routes.codegraph.codegraph_service.query_cli",
                new_callable=AsyncMock,
                return_value={"nodes": []},
            ) as mock_query,
        ):
            app_client.post(
                f"/api/codegraph/repos/{FAKE_REPO_ID}/query",
                json={"command": "callers", "args": ["MyClass.method"]},
            )

        mock_query.assert_awaited_once_with(
            "callers",
            ["MyClass.method"],
            FAKE_REPO_ID,
        )
