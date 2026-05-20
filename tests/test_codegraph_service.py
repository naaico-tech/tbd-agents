"""Unit tests for CodeGraphService.

All async tests run automatically via ``asyncio_mode = "auto"`` (configured in
pyproject.toml).  The sidecar HTTP calls are mocked via ``httpx.AsyncClient``
so the suite needs no running sidecar, database, git binary, or codegraph CLI.
"""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.models.codegraph_repo import CodeGraphRepoStatus
from app.services.codegraph_service import CodeGraphService, _slugify

# ── Constants ─────────────────────────────────────────────────────────────────

FAKE_REPO_ID = "507f1f77bcf86cd799439011"
FAKE_MCP_ID = "507f1f77bcf86cd799439012"


# ── Fake object helpers ───────────────────────────────────────────────────────


def _fake_repo(
    repo_id: str = FAKE_REPO_ID,
    name: str = "test-repo",
    status: CodeGraphRepoStatus = CodeGraphRepoStatus.PENDING,
    mcp_server_id: str | None = None,
    local_path: str = "",
) -> MagicMock:
    """Return a MagicMock that behaves like a ``CodeGraphRepo`` document."""
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


def _fake_mcp_server(
    mcp_id: str = FAKE_MCP_ID,
    name: str = "code-graph-test-repo",
) -> MagicMock:
    """Return a MagicMock that behaves like an ``McpServer`` document."""
    mcp = MagicMock()
    mcp.id = mcp_id
    mcp.name = name
    mcp.delete = AsyncMock()
    mcp.insert = AsyncMock()
    return mcp


def _make_mcp_cls(
    find_one_result: MagicMock | None,
    instance: MagicMock | None = None,
) -> MagicMock:
    """Build a mock ``McpServer`` class with configurable find_one / constructor."""
    mock_cls = MagicMock()
    mock_cls.find_one = AsyncMock(return_value=find_one_result)
    mock_cls.get = AsyncMock(return_value=find_one_result)
    if instance is not None:
        mock_cls.return_value = instance
    return mock_cls


def _make_httpx_client(
    post_json: dict | None = None,
    get_responses: list[dict] | None = None,
    delete_status: int = 204,
    raise_on_post: Exception | None = None,
) -> MagicMock:
    """Build a mock ``httpx.AsyncClient`` context manager.

    Parameters
    ----------
    post_json:
        JSON dict returned by ``client.post()``.
    get_responses:
        Sequence of JSON dicts returned by successive ``client.get()`` calls.
        Each poll consumes one entry; the last entry is repeated when exhausted.
    delete_status:
        HTTP status code returned by ``client.delete()``.
    raise_on_post:
        If set, ``client.post()`` raises this exception.
    """
    client = AsyncMock()

    # ── POST ──────────────────────────────────────────────────────────────────
    post_resp = MagicMock()
    if raise_on_post is not None:
        client.post = AsyncMock(side_effect=raise_on_post)
    else:
        post_resp.json = MagicMock(return_value=post_json or {})
        post_resp.raise_for_status = MagicMock()
        client.post = AsyncMock(return_value=post_resp)

    # ── GET (polling) ─────────────────────────────────────────────────────────
    _get_responses = list(get_responses or [{"status": "ready", "localPath": "/opt/codegraph_repos/test_repo"}])

    poll_call_count = 0

    async def _poll(*args, **kwargs):
        nonlocal poll_call_count
        idx = min(poll_call_count, len(_get_responses) - 1)
        poll_call_count += 1
        resp = MagicMock()
        resp.json = MagicMock(return_value=_get_responses[idx])
        resp.raise_for_status = MagicMock()
        return resp

    client.get = _poll

    # ── DELETE ────────────────────────────────────────────────────────────────
    del_resp = MagicMock()
    del_resp.status_code = delete_status
    del_resp.raise_for_status = MagicMock()
    client.delete = AsyncMock(return_value=del_resp)

    # Make the client usable as an async context manager.
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# ── Service singleton under test ──────────────────────────────────────────────

_service = CodeGraphService()


# ── Tests: _slugify ───────────────────────────────────────────────────────────


class TestSlugify:
    def test_replaces_spaces_with_underscores(self):
        assert _slugify("my repo") == "my_repo"

    def test_replaces_slashes_with_underscores(self):
        assert _slugify("org/repo") == "org_repo"

    def test_strips_unsafe_characters(self):
        assert _slugify("my-repo!@#") == "my-repo"

    def test_preserves_dots_and_hyphens(self):
        assert _slugify("my.repo-v1") == "my.repo-v1"


# ── Tests: index_repository ───────────────────────────────────────────────────


class TestIndexRepository:
    """Tests for ``CodeGraphService.index_repository``."""

    async def test_happy_path_transitions_to_ready(self):
        """Successful sidecar flow sets status=READY, populates indexed_at and mcp_server_id."""
        repo = _fake_repo()
        mcp = _fake_mcp_server()
        mock_mcp_cls = _make_mcp_cls(find_one_result=None, instance=mcp)

        http_client = _make_httpx_client(
            post_json={"slug": "test_repo", "localPath": "/opt/codegraph_repos/test_repo"},
            get_responses=[{"status": "ready", "localPath": "/opt/codegraph_repos/test_repo"}],
        )

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.McpServer", mock_mcp_cls),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=http_client),
            patch("app.services.codegraph_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            await _service.index_repository(
                repo_url="https://github.com/test/repo",
                name="test-repo",
                repo_id=FAKE_REPO_ID,
            )

        assert repo.status == CodeGraphRepoStatus.READY
        assert repo.indexed_at is not None
        assert repo.mcp_server_id == str(mcp.id)
        assert repo.save.await_count >= 2

    async def test_sidecar_http_error_transitions_to_error(self):
        """A network error reaching the sidecar sets status=ERROR."""
        repo = _fake_repo()
        http_client = _make_httpx_client(
            raise_on_post=httpx.ConnectError("Connection refused"),
        )

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=http_client),
        ):
            await _service.index_repository(
                repo_url="https://github.com/test/repo",
                name="test-repo",
                repo_id=FAKE_REPO_ID,
            )

        assert repo.status == CodeGraphRepoStatus.ERROR
        assert repo.error_message is not None
        assert "sidecar" in repo.error_message.lower()

    async def test_sidecar_error_status_transitions_to_error(self):
        """When the sidecar reports status='error', the repo transitions to ERROR."""
        repo = _fake_repo()
        http_client = _make_httpx_client(
            post_json={"slug": "test_repo", "localPath": "/opt/codegraph_repos/test_repo"},
            get_responses=[{"status": "error", "error": "git clone failed: not found"}],
        )

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=http_client),
            patch("app.services.codegraph_service.asyncio.sleep", new_callable=AsyncMock),
        ):
            with pytest.raises(RuntimeError, match="git clone failed"):
                await _service.index_repository(
                    repo_url="https://github.com/test/repo",
                    name="test-repo",
                    repo_id=FAKE_REPO_ID,
                )

        assert repo.status == CodeGraphRepoStatus.ERROR

    async def test_polls_until_sidecar_reports_ready(self):
        """Status transitions are mirrored through multiple poll cycles before ready."""
        repo = _fake_repo()
        mcp = _fake_mcp_server()
        mock_mcp_cls = _make_mcp_cls(find_one_result=None, instance=mcp)

        http_client = _make_httpx_client(
            post_json={"slug": "test_repo", "localPath": "/opt/codegraph_repos/test_repo"},
            get_responses=[
                {"status": "cloning"},
                {"status": "indexing"},
                {"status": "ready", "localPath": "/opt/codegraph_repos/test_repo"},
            ],
        )

        sleep_mock = AsyncMock()

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.McpServer", mock_mcp_cls),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=http_client),
            patch("app.services.codegraph_service.asyncio.sleep", sleep_mock),
        ):
            await _service.index_repository(
                repo_url="https://github.com/test/repo",
                name="test-repo",
                repo_id=FAKE_REPO_ID,
            )

        # Should have polled 3 times (cloning → indexing → ready)
        assert sleep_mock.await_count == 3
        assert repo.status == CodeGraphRepoStatus.READY

    async def test_raises_value_error_when_repo_document_not_found(self):
        """Raises ValueError immediately when the CodeGraphRepo document is missing."""
        with patch(
            "app.services.codegraph_service.CodeGraphRepo.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ValueError, match="not found"):
                await _service.index_repository(
                    repo_url="https://github.com/test/repo",
                    name="test-repo",
                    repo_id=FAKE_REPO_ID,
                )


# ── Tests: ensure_mcp_server ──────────────────────────────────────────────────


class TestEnsureMcpServer:
    """Tests for ``CodeGraphService.ensure_mcp_server``."""

    async def test_creates_sse_record_when_none_exists(self):
        """Inserts a new SSE McpServer document when find_one returns None."""
        from app.models.mcp_server import TransportType

        repo = _fake_repo()
        mcp = _fake_mcp_server(name="code-graph-test-repo")
        mock_mcp_cls = _make_mcp_cls(find_one_result=None, instance=mcp)

        with patch("app.services.codegraph_service.McpServer", mock_mcp_cls):
            result = await _service.ensure_mcp_server(repo)

        mock_mcp_cls.find_one.assert_awaited_once()
        mcp.insert.assert_awaited_once()
        assert result is mcp
        # Verify the constructor was called with SSE transport
        ctor_kwargs = mock_mcp_cls.call_args.kwargs
        assert ctor_kwargs.get("transport_type") == TransportType.SSE
        assert "url" in ctor_kwargs.get("connection_config", {})

    async def test_returns_existing_record_without_insert(self):
        """Returns the existing McpServer without a new insert when one is found."""
        repo = _fake_repo()
        existing_mcp = _fake_mcp_server(name="code-graph-test-repo")
        mock_mcp_cls = _make_mcp_cls(find_one_result=existing_mcp)

        with patch("app.services.codegraph_service.McpServer", mock_mcp_cls):
            result = await _service.ensure_mcp_server(repo)

        mock_mcp_cls.find_one.assert_awaited_once()
        existing_mcp.insert.assert_not_awaited()
        assert result is existing_mcp

    async def test_sse_url_contains_slug(self):
        """The SSE URL registered in McpServer contains the repo slug."""
        repo = _fake_repo(name="my org/my repo")
        mcp = _fake_mcp_server()
        mock_mcp_cls = _make_mcp_cls(find_one_result=None, instance=mcp)

        with patch("app.services.codegraph_service.McpServer", mock_mcp_cls):
            await _service.ensure_mcp_server(repo)

        ctor_kwargs = mock_mcp_cls.call_args.kwargs
        sse_url = ctor_kwargs["connection_config"]["url"]
        # Slug is "my_org_my_repo" — no spaces or slashes
        assert "my_org_my_repo" in sse_url
        assert sse_url.endswith("/sse")

    async def test_is_idempotent_across_two_calls(self):
        """Second call returns the existing record; only one insert ever happens."""
        repo = _fake_repo()
        mcp_instance = _fake_mcp_server(name="code-graph-test-repo")
        mock_mcp_cls = MagicMock()
        mock_mcp_cls.find_one = AsyncMock(side_effect=[None, mcp_instance])
        mock_mcp_cls.return_value = mcp_instance

        with patch("app.services.codegraph_service.McpServer", mock_mcp_cls):
            await _service.ensure_mcp_server(repo)
            await _service.ensure_mcp_server(repo)

        assert mcp_instance.insert.await_count == 1


# ── Tests: query_cli ──────────────────────────────────────────────────────────


class TestQueryCli:
    """Tests for ``CodeGraphService.query_cli``."""

    async def test_returns_parsed_json_from_sidecar(self):
        """Returns the JSON dict from the sidecar's /query endpoint."""
        expected = {"results": [{"file": "app/main.py", "line": 10}]}
        repo = _fake_repo()

        resp = MagicMock()
        resp.json = MagicMock(return_value=expected)
        resp.raise_for_status = MagicMock()
        client = AsyncMock()
        client.post = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            result = await _service.query_cli(
                command="search",
                args=["def create_app"],
                repo_id=FAKE_REPO_ID,
            )

        assert result == expected

    async def test_raises_value_error_when_repo_not_found(self):
        """Raises ValueError when the CodeGraphRepo document does not exist."""
        with patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await _service.query_cli(command="search", args=[], repo_id=FAKE_REPO_ID)

    async def test_posts_to_correct_sidecar_endpoint(self):
        """POSTs to /repos/{slug}/query with command and args in the body."""
        repo = _fake_repo(name="test-repo")

        resp = MagicMock()
        resp.json = MagicMock(return_value={"nodes": []})
        resp.raise_for_status = MagicMock()
        client = AsyncMock()
        client.post = AsyncMock(return_value=resp)
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            await _service.query_cli(command="callers", args=["MyClass.my_method"], repo_id=FAKE_REPO_ID)

        called_url = client.post.call_args.args[0]
        called_body = client.post.call_args.kwargs.get("json", {})
        # _slugify("test-repo") preserves the hyphen → "test-repo"
        assert "test-repo" in called_url
        assert called_body["command"] == "callers"
        assert "MyClass.my_method" in called_body["args"]


# ── Tests: remove_repository ──────────────────────────────────────────────────


class TestRemoveRepository:
    """Tests for ``CodeGraphService.remove_repository``."""

    async def test_deletes_mcp_server_record_and_repo_document(self):
        """Awaits delete() on both the McpServer and the CodeGraphRepo."""
        mcp = _fake_mcp_server()
        repo = _fake_repo(mcp_server_id=FAKE_MCP_ID)

        client = _make_httpx_client()

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.McpServer.get", new_callable=AsyncMock, return_value=mcp),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            await _service.remove_repository(FAKE_REPO_ID)

        mcp.delete.assert_awaited_once()
        repo.delete.assert_awaited_once()

    async def test_raises_value_error_when_repo_not_found(self):
        """Raises ValueError when the CodeGraphRepo document does not exist."""
        with patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match="not found"):
                await _service.remove_repository(FAKE_REPO_ID)

    async def test_skips_mcp_delete_when_no_mcp_server_id(self):
        """Does not query or delete McpServer when mcp_server_id is None."""
        repo = _fake_repo(mcp_server_id=None)
        client = _make_httpx_client()

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.McpServer.get", new_callable=AsyncMock) as mock_mcp_get,
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            await _service.remove_repository(FAKE_REPO_ID)

        mock_mcp_get.assert_not_awaited()
        repo.delete.assert_awaited_once()

    async def test_skips_mcp_delete_when_mcp_server_record_missing(self):
        """Gracefully handles the case where mcp_server_id is set but the record is gone."""
        repo = _fake_repo(mcp_server_id=FAKE_MCP_ID)
        client = _make_httpx_client()

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.McpServer.get", new_callable=AsyncMock, return_value=None),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            await _service.remove_repository(FAKE_REPO_ID)

        repo.delete.assert_awaited_once()

    async def test_sidecar_delete_failure_is_ignored(self):
        """HTTP errors from the sidecar DELETE call do not abort repo record removal."""
        repo = _fake_repo(mcp_server_id=None)
        client = AsyncMock()
        client.delete = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("app.services.codegraph_service.CodeGraphRepo.get", new_callable=AsyncMock, return_value=repo),
            patch("app.services.codegraph_service.httpx.AsyncClient", return_value=client),
        ):
            await _service.remove_repository(FAKE_REPO_ID)

        # Should still delete the DB record even if sidecar call failed
        repo.delete.assert_awaited_once()


# ── Tests: list_repositories ──────────────────────────────────────────────────


class TestListRepositories:
    """Tests for ``CodeGraphService.list_repositories``."""

    async def test_returns_all_documents(self):
        """Delegates to CodeGraphRepo.find_all().to_list() and returns the result."""
        repos = [_fake_repo(repo_id=f"507f1f77bcf86cd79943901{i}") for i in range(3)]

        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=repos)

        with patch("app.services.codegraph_service.CodeGraphRepo.find_all", return_value=mock_find):
            result = await _service.list_repositories()

        assert result == repos
        mock_find.to_list.assert_awaited_once()

    async def test_returns_empty_list_when_no_repos(self):
        """Returns an empty list when no repositories are registered."""
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[])

        with patch("app.services.codegraph_service.CodeGraphRepo.find_all", return_value=mock_find):
            result = await _service.list_repositories()

        assert result == []

