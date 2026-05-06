"""Tests for POST /api/chat/start — workflow-backed chat session endpoint.

Auth note: FastAPI's Depends() captures get_current_user at import time, so
the correct override mechanism is app.dependency_overrides.  The autouse
fixture 'override_auth' sets a "testuser" override for every test in this
module and tears it down afterwards.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main import app as _app

# ── Constants ─────────────────────────────────────────────────────────────────

FAKE_AGENT_ID = "6601a1b2c3d4e5f607890abc"
FAKE_WORKFLOW_ID = "6601a1b2c3d4e5f607890abd"


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


def _fake_agent(name: str = "My Agent"):
    return SimpleNamespace(
        id=FAKE_AGENT_ID,
        name=name,
        model="gpt-4.1",
        description="A test agent",
        system_prompt="You are helpful.",
    )


def _fake_workflow_instance(github_user: str = "testuser", title: str = "Chat: My Agent"):
    """Return a mock Workflow document instance with async insert."""
    ns = MagicMock()
    ns.id = FAKE_WORKFLOW_ID
    ns.title = title
    ns.agent_id = FAKE_AGENT_ID
    ns.github_user = github_user
    ns.status = "active"
    ns.insert = AsyncMock()
    return ns


def _make_workflow_cls(find_one_result, instance=None):
    """Return a MagicMock that looks like the Workflow class.

    - ``find_one_result`` is what ``await Workflow.find_one(...)`` returns.
    - ``instance`` is the object returned when ``Workflow(...)`` is called
      (only needed when testing the create-new-workflow path).
    """
    mock_cls = MagicMock()
    mock_cls.find_one = AsyncMock(return_value=find_one_result)
    # Make field attribute comparisons work (used in find_one query args)
    mock_cls.github_user = MagicMock()
    mock_cls.agent_id = MagicMock()
    mock_cls.title = MagicMock()
    mock_cls.status = MagicMock()
    if instance is not None:
        mock_cls.return_value = instance
    return mock_cls


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestChatStart:
    """Tests for POST /api/chat/start."""

    def test_creates_new_workflow_when_none_exists(self, app_client):
        """Returns a new workflow_id when no chat workflow exists for this agent/user."""
        agent = _fake_agent()
        new_wf = _fake_workflow_instance()
        mock_wf_cls = _make_workflow_cls(find_one_result=None, instance=new_wf)

        with (
            patch("app.api.routes.chat.Agent.get", new_callable=AsyncMock, return_value=agent),
            patch("app.api.routes.chat.Workflow", mock_wf_cls),
        ):
            resp = app_client.post("/api/chat/start", json={"agent_id": FAKE_AGENT_ID})

        assert resp.status_code == 200
        data = resp.json()
        assert data["workflow_id"] == str(FAKE_WORKFLOW_ID)
        assert data["agent_name"] == "My Agent"
        assert data["agent_id"] == str(FAKE_AGENT_ID)
        new_wf.insert.assert_awaited_once()

    def test_returns_existing_workflow_when_found(self, app_client):
        """Returns the existing workflow_id when an active chat workflow is found."""
        agent = _fake_agent()
        existing_wf = _fake_workflow_instance()
        mock_wf_cls = _make_workflow_cls(find_one_result=existing_wf)

        with (
            patch("app.api.routes.chat.Agent.get", new_callable=AsyncMock, return_value=agent),
            patch("app.api.routes.chat.Workflow", mock_wf_cls),
        ):
            resp = app_client.post("/api/chat/start", json={"agent_id": FAKE_AGENT_ID})

        assert resp.status_code == 200
        data = resp.json()
        assert data["workflow_id"] == str(FAKE_WORKFLOW_ID)
        assert data["agent_name"] == "My Agent"
        assert data["agent_id"] == str(FAKE_AGENT_ID)
        # insert should NOT be called — we returned an existing workflow
        existing_wf.insert.assert_not_awaited()

    def test_returns_404_when_agent_not_found(self, app_client):
        """Returns HTTP 404 when the requested agent_id does not exist."""
        with patch("app.api.routes.chat.Agent.get", new_callable=AsyncMock, return_value=None):
            resp = app_client.post("/api/chat/start", json={"agent_id": FAKE_AGENT_ID})

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Agent not found"

    def test_returns_404_when_agent_get_raises(self, app_client):
        """Returns HTTP 404 when Agent.get raises an exception (e.g. invalid ObjectId)."""
        with patch(
            "app.api.routes.chat.Agent.get",
            new_callable=AsyncMock,
            side_effect=Exception("Invalid ObjectId"),
        ):
            resp = app_client.post("/api/chat/start", json={"agent_id": FAKE_AGENT_ID})

        assert resp.status_code == 404
        assert resp.json()["detail"] == "Agent not found"

    def test_chat_title_uses_agent_name(self, app_client):
        """Workflow is created with title 'Chat: {agent.name}'."""
        agent = _fake_agent(name="Code Review Bot")
        new_wf = _fake_workflow_instance(title="Chat: Code Review Bot")
        captured_kwargs: dict = {}

        def _capture(**kwargs):
            captured_kwargs.update(kwargs)
            return new_wf

        mock_wf_cls = _make_workflow_cls(find_one_result=None)
        mock_wf_cls.side_effect = _capture

        with (
            patch("app.api.routes.chat.Agent.get", new_callable=AsyncMock, return_value=agent),
            patch("app.api.routes.chat.Workflow", mock_wf_cls),
        ):
            resp = app_client.post("/api/chat/start", json={"agent_id": FAKE_AGENT_ID})

        assert resp.status_code == 200
        assert captured_kwargs.get("title") == "Chat: Code Review Bot"
