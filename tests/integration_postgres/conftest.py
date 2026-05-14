"""Shared fixtures for PostgreSQL integration tests.

Connects to a *real* PostgreSQL database and exercises the full
PostgresDocument stack without mocking the DB layer.

Prerequisites — start a test PostgreSQL container before running:

    docker compose -f docker-compose.test.yml up -d pgvector-test

Then run the tests:

    DB_BACKEND=postgres \\
      TEST_POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5433/tbd_agents_integration_test \\
      TOKEN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \\
      pytest tests/integration/postgres/ -v

The ``DB_BACKEND=postgres`` env var **must** be set before any app model
imports so that models load their ``PostgresDocument`` base class.  This
conftest enforces that contract at the top of the file.

The existing tbd-pgvector production container can also be used during
local development by pointing ``TEST_POSTGRES_URI`` at port 5432 and
using a dedicated test database name:

    TEST_POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents_int_test
"""
from __future__ import annotations

import os

# IMPORTANT: set DB_BACKEND BEFORE any app model imports so the conditional
# ``_POSTGRES = os.environ.get("DB_BACKEND", "mongo") == "postgres"`` at the
# top of each model module evaluates to True.
os.environ["DB_BACKEND"] = "postgres"

from datetime import UTC, datetime  # noqa: E402 (after env-var set)
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import text  # noqa: E402

# ---------------------------------------------------------------------------
# DB helpers — imported AFTER DB_BACKEND is set
# ---------------------------------------------------------------------------

from app.db_postgres import (  # noqa: E402
    COLLECTIONS,
    close_postgres,
    get_engine,
    init_postgres,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TEST_POSTGRES_URI = os.getenv(
    "TEST_POSTGRES_URI",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents_integration_test",
)
TEST_DB_NAME = TEST_POSTGRES_URI.rsplit("/", 1)[-1]

# Override the settings URI so PostgresDocument uses the test database.
os.environ["POSTGRES_URI"] = TEST_POSTGRES_URI


def _create_test_db_if_missing() -> None:
    """Create the test database synchronously before async fixtures run.

    Uses psycopg2 (synchronous driver) against the ``postgres`` maintenance
    database.  Only called once at conftest import time.
    """
    try:
        import psycopg2
        from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    except ImportError:
        # psycopg2 not installed — the container must already have the DB.
        return

    # Build a connection string for the admin ``postgres`` database
    admin_uri = TEST_POSTGRES_URI.replace(
        f"/{TEST_DB_NAME}", "/postgres"
    ).replace("postgresql+asyncpg://", "postgresql://")

    try:
        conn = psycopg2.connect(admin_uri)
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        )
        if not cur.fetchone():
            cur.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
        cur.close()
        conn.close()
    except Exception:
        # If we cannot connect (e.g., psycopg2 not available), the test run
        # will fail with a clear "database does not exist" error — acceptable.
        pass


_create_test_db_if_missing()

# ---------------------------------------------------------------------------
# Per-test DB setup/teardown
#
# pytest-asyncio creates a new event loop per test function.  SQLAlchemy's
# AsyncEngine is bound to the loop that created it, so a session-scoped engine
# would break on the second test.  The fix: close_postgres() before every test
# to reset the singleton, let init_postgres() create a fresh engine in the
# current loop, and close again afterwards.  CREATE TABLE IF NOT EXISTS is a
# fast no-op after the first test, so this adds negligible overhead.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
async def pg_db():
    """Set up (or verify) schema before each test; truncate afterwards.

    Steps:
      1. close_postgres() — disposes any engine from a prior loop.
      2. init_postgres()  — creates tables (IF NOT EXISTS) in current loop.
         settings.postgres_uri already points at TEST_POSTGRES_URI via the
         POSTGRES_URI env var set at the top of this module.
      3. yield            — run the test.
      4. Truncate all tables for test isolation.
      5. close_postgres() — dispose engine cleanly.
    """
    await close_postgres()
    await init_postgres()

    yield  # ← test runs here

    engine = await get_engine()
    async with engine.begin() as conn:
        for collection in COLLECTIONS:
            await conn.execute(
                text(f"TRUNCATE TABLE {collection} RESTART IDENTITY CASCADE")
            )

    await close_postgres()


# ---------------------------------------------------------------------------
# Mock Redis / event_bus — same strategy as MongoDB integration conftest
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_event_bus():
    """Patch event_bus to record published events in-memory."""
    events: list[tuple[str, str, dict]] = []

    async def _publish(wf_id: str, event_type: str, data: dict) -> None:
        events.append((wf_id, event_type, data))

    async def _subscribe(wf_id: str):
        yield None

    async def _set_halt(wf_id: str) -> None:
        pass

    async def _check_halt(wf_id: str) -> bool:
        return False

    async def _clear_halt(wf_id: str) -> None:
        pass

    bus = MagicMock()
    bus.publish = AsyncMock(side_effect=_publish)
    bus.subscribe = _subscribe
    bus.set_halt = AsyncMock(side_effect=_set_halt)
    bus.check_halt = AsyncMock(side_effect=_check_halt)
    bus.clear_halt = AsyncMock(side_effect=_clear_halt)
    bus.events = events

    with (
        patch("app.core.agent_engine.event_bus", bus),
        patch("app.core.event_bus.publish", bus.publish),
        patch("app.core.event_bus.subscribe", bus.subscribe),
        patch("app.core.event_bus.set_halt", bus.set_halt),
        patch("app.core.event_bus.check_halt", bus.check_halt),
        patch("app.core.event_bus.clear_halt", bus.clear_halt),
    ):
        yield bus


# ---------------------------------------------------------------------------
# Celery eager mode
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def celery_eager():
    """Run Celery tasks synchronously in-process."""
    from app.celery_app import celery

    celery.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield
    celery.conf.update(task_always_eager=False, task_eager_propagates=False)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

TEST_GITHUB_USER = {"login": "pgintegrationuser", "id": 99, "name": "PG Integration User"}


@pytest.fixture(autouse=True)
def mock_auth():
    """Bypass GitHub token validation in all PostgreSQL integration tests."""
    with patch(
        "app.api.deps.validate_github_token",
        new_callable=AsyncMock,
        return_value=TEST_GITHUB_USER,
    ):
        yield


# ---------------------------------------------------------------------------
# Document factory helpers — mirror the MongoDB conftest factories
# ---------------------------------------------------------------------------


async def create_agent(**overrides) -> "Agent":  # noqa: F821
    """Insert an Agent document with sensible defaults."""
    from app.models.agent import Agent

    data = {
        "name": "pg-integration-agent",
        "description": "Agent for PostgreSQL integration tests",
        "system_prompt": "You are a helpful assistant.",
        "model": "gpt-4.1",
        "mcp_server_ids": [],
        "mcp_server_tags": [],
        "knowledge_source_ids": [],
        "knowledge_tags": [],
        "skill_ids": [],
        "builtin_tools": [],
        "tool_definitions": [],
        "custom_tool_ids": [],
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    data.update(overrides)
    agent = Agent(**data)
    await agent.insert()
    return agent


async def create_workflow(agent, **overrides) -> "Workflow":  # noqa: F821
    """Insert a Workflow document linked to an agent."""
    from app.models.workflow import Workflow

    data = {
        "agent_id": str(agent.id),
        "github_user": TEST_GITHUB_USER["login"],
        "model": "gpt-4.1",
        "max_turns": 25,
        "skill_ids": [],
        "guardrail_ids": [],
        "guardrail_tags": [],
    }
    data.update(overrides)
    wf = Workflow(**data)
    await wf.insert()
    return wf


async def create_task(workflow, **overrides) -> "TaskExecution":  # noqa: F821
    """Insert a TaskExecution document for a workflow."""
    from app.models.task_execution import TaskExecution, TaskStatus

    data = {
        "workflow_id": str(workflow.id),
        "prompt": "integration test prompt",
        "status": TaskStatus.PENDING,
    }
    data.update(overrides)
    task = TaskExecution(**data)
    await task.insert()
    return task


async def create_skill(**overrides) -> "Skill":  # noqa: F821
    """Insert a Skill document."""
    from app.models.skill import Skill

    data = {
        "name": "pg-test-skill",
        "description": "A PostgreSQL integration test skill",
        "instructions": "Always respond politely.",
        "tags": [],
    }
    data.update(overrides)
    skill = Skill(**data)
    await skill.insert()
    return skill
