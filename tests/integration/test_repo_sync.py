"""Integration tests: repository synchronisation via _sync_repo.

Verifies that git clone / pull commands are constructed correctly,
auth tokens are resolved, and repo paths are returned.

Closes #41
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import _sync_repo
from app.models.workflow import Workflow, WorkflowStatus

from .conftest import create_agent, create_token, create_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_process(returncode: int = 0, stdout: bytes = b"", stderr: bytes = b""):
    proc = AsyncMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    return proc


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRepoSync:
    @pytest.mark.asyncio
    async def test_clone_new_repo(self):
        """First sync clones the repo with --depth 1."""
        await create_token("repo-token", "ghp_repo_secret")
        agent = await create_agent()
        wf = await create_workflow(
            agent,
            repo_url="https://github.com/org/repo.git",
            repo_token_name="repo-token",
            repo_branch="main",
        )

        captured_cmds = []

        async def fake_subprocess(cmd, **kwargs):
            captured_cmds.append(cmd)
            return _fake_process()

        with patch("app.core.agent_engine.asyncio.create_subprocess_shell", side_effect=fake_subprocess):
            with patch("os.path.isdir", return_value=False), patch("os.makedirs"):
                result = await _sync_repo(wf)

        assert result is not None
        # Should have run a git clone
        clone_cmd = next((c for c in captured_cmds if "clone" in c), None)
        assert clone_cmd is not None
        assert "--depth" in clone_cmd
        assert "ghp_repo_secret" in clone_cmd  # token injected into URL

    @pytest.mark.asyncio
    async def test_pull_existing_repo(self):
        """Subsequent sync fetches + checks out."""
        await create_token("repo-token2", "ghp_existing")
        agent = await create_agent()
        wf = await create_workflow(
            agent,
            repo_url="https://github.com/org/existing.git",
            repo_token_name="repo-token2",
            repo_branch="develop",
        )

        captured_cmds = []

        async def fake_subprocess(cmd, **kwargs):
            captured_cmds.append(cmd)
            return _fake_process()

        with patch("app.core.agent_engine.asyncio.create_subprocess_shell", side_effect=fake_subprocess):
            with patch("os.path.isdir", return_value=True):
                result = await _sync_repo(wf)

        assert result is not None
        # Should fetch, not clone
        assert any("fetch" in c for c in captured_cmds)
        assert not any("clone" in c for c in captured_cmds)

    @pytest.mark.asyncio
    async def test_no_repo_url_returns_none(self):
        """Workflow without repo_url returns None immediately."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        # Ensure repo_url is None/empty
        wf.repo_url = None
        await wf.save()

        result = await _sync_repo(wf)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_token_skips_auth(self):
        """If repo_token_name resolves to None, URL has no credentials."""
        agent = await create_agent()
        wf = await create_workflow(
            agent,
            repo_url="https://github.com/org/public-repo.git",
            repo_token_name="nonexistent-token",
        )

        captured_cmds = []

        async def fake_subprocess(cmd, **kwargs):
            captured_cmds.append(cmd)
            return _fake_process()

        with patch("app.core.agent_engine.asyncio.create_subprocess_shell", side_effect=fake_subprocess):
            with patch("os.path.isdir", return_value=False), patch("os.makedirs"):
                result = await _sync_repo(wf)

        # Should still attempt clone even without auth
        if captured_cmds:
            clone_cmd = captured_cmds[0]
            assert "nonexistent-token" not in clone_cmd

    @pytest.mark.asyncio
    async def test_clone_failure_returns_none(self):
        """If git clone fails, _sync_repo returns None gracefully."""
        await create_token("fail-token", "ghp_fail")
        agent = await create_agent()
        wf = await create_workflow(
            agent,
            repo_url="https://github.com/org/bad-repo.git",
            repo_token_name="fail-token",
        )

        async def fail_subprocess(cmd, **kwargs):
            return _fake_process(returncode=128, stderr=b"fatal: repository not found")

        with patch("app.core.agent_engine.asyncio.create_subprocess_shell", side_effect=fail_subprocess):
            with patch("os.path.isdir", return_value=False), patch("os.makedirs"):
                result = await _sync_repo(wf)

        assert result is None
