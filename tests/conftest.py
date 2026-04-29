"""Shared fixtures for the test suite."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Event loop ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Mock settings ────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_settings():
    """Provide a Settings-like object with test defaults."""
    from app.config import Settings

    return Settings(
        mongo_uri="mongodb://localhost:27017",
        mongo_db_name="test_db",
        github_token="ghp_test_token_1234",
        redis_url="redis://localhost:6379/0",
        token_encryption_key=None,
        otel_endpoint="",
        otel_http_endpoint="",
    )


# ── FastAPI test client ─────────────────────────────────────────────────────


@pytest.fixture()
def app_client():
    """Return a TestClient with DB init and auth mocked out."""
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.init_telemetry"),
        patch("app.main.Instrumentator") as mock_instr,
        # Prevent plugin loader from hitting uninitialised Beanie collections
        patch("app.main.plugin_loader.load_plugins_from_config", new_callable=AsyncMock),
    ):
        mock_instr.return_value.instrument.return_value.expose = MagicMock()
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as client:
            yield client


# ── GitHub user stub ─────────────────────────────────────────────────────────


@pytest.fixture()
def github_user():
    """Standard test GitHub user dict."""
    return {"login": "testuser", "id": 123, "name": "Test User"}


# ── Fake Beanie documents ───────────────────────────────────────────────────


def _fake_id():
    """Return a fake 24-char hex ObjectId string."""
    return "6601a1b2c3d4e5f607890abc"


@pytest.fixture()
def sample_agent():
    """Return a dict representing an Agent document."""
    return {
        "id": _fake_id(),
        "name": "Test Agent",
        "description": "A test agent",
        "system_prompt": "You are a test assistant.",
        "model": "gpt-4.1",
        "mcp_server_ids": [],
        "mcp_server_tags": [],
        "tool_definitions": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }


@pytest.fixture()
def sample_workflow(sample_agent, github_user):
    """Return a dict representing a Workflow document."""
    return {
        "id": _fake_id(),
        "title": "Test Workflow",
        "agent_id": sample_agent["id"],
        "github_user": github_user["login"],
        "model": "gpt-4.1",
        "max_turns": 5,
        "current_turn": 0,
        "session_id": None,
        "skill_ids": [],
        "messages": [],
        "logs": [],
        "status": "active",
        "output_format": "json",
        "infinite_session": True,
        "reasoning_effort": None,
        "guardrail_ids": [],
        "guardrail_tags": [],
        "repo_url": None,
        "repo_branch": None,
        "repo_token_name": None,
        "output_mcps": [],
        "usage": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
