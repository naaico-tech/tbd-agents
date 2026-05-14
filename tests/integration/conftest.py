"""Shared fixtures for integration tests.

Provides a real MongoDB database (via Motor + Beanie) and a mock Redis
layer so tests exercise the full data and service stack without needing
external infrastructure at import time.

Start MongoDB/Redis before running:
    docker compose -f docker-compose.test.yml up -d
    TOKEN_ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())") \
      TEST_MONGO_URI=mongodb://localhost:27018 REDIS_URL=redis://localhost:6380 \
      pytest tests/integration/ -v
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.models.agent import Agent
from app.models.guardrail import Guardrail
from app.models.knowledge_item import KnowledgeItem
from app.models.knowledge_source import KnowledgeSource
from app.models.mcp_server import McpServer
from app.models.memory import Memory
from app.models.provider import Provider, ProviderType
from app.models.skill import Skill
from app.models.task_execution import TaskExecution
from app.models.token import Token
from app.models.workflow import Workflow

# ---------------------------------------------------------------------------
# MongoDB setup
# ---------------------------------------------------------------------------

MONGO_URI = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27018")
MONGO_DB = "tbd_agents_integration_test"

ALL_MODELS = [
    Agent, Guardrail, KnowledgeItem, KnowledgeSource, McpServer,
    Memory, Provider, Skill, TaskExecution, Token, Workflow,
]


@pytest.fixture(autouse=True)
async def init_db():
    """Initialise Beanie with a clean database before each test.

    Creates a fresh Motor client per test to avoid event-loop conflicts
    between pytest-asyncio's function-scoped loops and session-scoped
    resources.
    """
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[MONGO_DB]
    await init_beanie(database=db, document_models=ALL_MODELS)
    yield
    # Drop all collections after each test for isolation
    for name in await db.list_collection_names():
        await db.drop_collection(name)
    client.close()


# ---------------------------------------------------------------------------
# Mock Redis / event_bus
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_event_bus():
    """Patch event_bus to record published events in-memory."""
    events: list[tuple[str, str, dict]] = []

    async def _publish(wf_id: str, event_type: str, data: dict) -> None:
        events.append((wf_id, event_type, data))

    async def _subscribe(wf_id: str):
        # Yield once then stop
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
    bus.events = events  # expose for assertions

    with patch("app.core.agent_engine.event_bus", bus), \
         patch("app.core.event_bus.publish", bus.publish), \
         patch("app.core.event_bus.subscribe", bus.subscribe), \
         patch("app.core.event_bus.set_halt", bus.set_halt), \
         patch("app.core.event_bus.check_halt", bus.check_halt), \
         patch("app.core.event_bus.clear_halt", bus.clear_halt):
        yield bus


# ---------------------------------------------------------------------------
# Celery eager mode
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def celery_eager():
    """Run Celery tasks synchronously in-process."""
    from app.celery_app import celery

    celery.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    yield
    celery.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
    )


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


TEST_GITHUB_USER = {"login": "integrationuser", "id": 42, "name": "Integration User"}


@pytest.fixture()
def auth_headers():
    """Return headers with a valid (mocked) GitHub token."""
    return {"Authorization": "Bearer ghp_test_integration_token"}


@pytest.fixture(autouse=True)
def mock_auth():
    """Bypass GitHub token validation in all integration tests."""
    with patch(
        "app.api.deps.validate_github_token",
        new_callable=AsyncMock,
        return_value=TEST_GITHUB_USER,
    ):
        yield


# ---------------------------------------------------------------------------
# HTTP test client
# ---------------------------------------------------------------------------


@pytest.fixture()
async def app_client():
    """Async HTTP client backed by the FastAPI app.

    Uses httpx.AsyncClient + ASGITransport so requests execute on the
    *same* event loop as the test (and therefore share the Motor/Beanie
    initialisation done by ``init_db``).
    """
    import httpx

    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.init_telemetry"),
        patch("app.main.Instrumentator") as mock_instr,
    ):
        mock_instr.return_value.instrument.return_value.expose = MagicMock()
        from app.main import app

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


async def create_agent(**overrides) -> Agent:
    """Insert an Agent document with sensible defaults."""
    data = {
        "name": "integration-agent",
        "description": "Agent for integration tests",
        "system_prompt": "You are a helpful assistant.",
        "model": "gpt-4.1",
        "mcp_server_ids": [],
        "mcp_server_tags": [],
        "knowledge_source_ids": [],
        "knowledge_tags": [],
        "skill_ids": [],
        "builtin_tools": [],
        "tool_definitions": [],
    }
    data.update(overrides)
    agent = Agent(**data)
    await agent.insert()
    return agent


async def create_provider(**overrides) -> Provider:
    """Insert a Provider document."""
    data = {
        "name": "test-provider",
        "provider_type": ProviderType.OPENAI,
        "api_key_token_name": "test-key",
    }
    data.update(overrides)
    provider = Provider(**data)
    await provider.insert()
    return provider


async def create_workflow(agent: Agent, **overrides) -> Workflow:
    """Insert a Workflow document linked to an agent."""
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


async def create_guardrail(**overrides) -> Guardrail:
    """Insert a Guardrail document.

    Accepts flat shorthand keys (forbidden_patterns, required_patterns,
    min_length, max_length, json_schema) and wraps them into the nested
    prompt_config / request_config expected by the model.
    """
    from app.models.guardrail import (
        GuardrailType,
        PromptGuardrailConfig,
        RequestGuardrailConfig,
    )

    # Pull flat shorthand keys before passing to model
    forbidden = overrides.pop("forbidden_patterns", None)
    required = overrides.pop("required_patterns", None)
    min_len = overrides.pop("min_length", None)
    max_len = overrides.pop("max_length", None)
    schema = overrides.pop("json_schema", None)

    gtype = overrides.get("guardrail_type", GuardrailType.PROMPT)

    data: dict = {
        "name": "test-guardrail",
        "guardrail_type": gtype,
    }
    data.update(overrides)

    # Build nested config from shorthands when not explicitly provided
    if gtype == GuardrailType.PROMPT and "prompt_config" not in data:
        cfg: dict = {}
        if forbidden is not None:
            cfg["forbidden_patterns"] = forbidden
        if required is not None:
            cfg["required_patterns"] = required
        if min_len is not None:
            cfg["min_length"] = min_len
        if max_len is not None:
            cfg["max_length"] = max_len
        data["prompt_config"] = PromptGuardrailConfig(**cfg)

    if gtype == GuardrailType.REQUEST and "request_config" not in data:
        if schema is not None:
            data["request_config"] = RequestGuardrailConfig(json_schema=schema)

    g = Guardrail(**data)
    await g.insert()
    return g


async def create_token(name: str, value: str) -> Token:
    """Insert an encrypted Token document."""
    from app.services.token_manager import encrypt_value

    token = Token(
        name=name,
        encrypted_value=encrypt_value(value),
        description="test token",
        created_by="integrationuser",
    )
    await token.insert()
    return token


async def create_mcp_server(**overrides) -> McpServer:
    """Insert an McpServer document."""
    data = {
        "name": "test-mcp",
        "transport_type": "stdio",
        "connection_config": {"command": "echo", "args": ["hello"]},
        "tags": [],
    }
    data.update(overrides)
    server = McpServer(**data)
    await server.insert()
    return server


async def create_skill(**overrides) -> Skill:
    """Insert a Skill document."""
    data = {
        "name": "test-skill",
        "description": "A test skill",
        "instructions": "Always respond politely.",
        "tags": [],
    }
    data.update(overrides)
    skill = Skill(**data)
    await skill.insert()
    return skill
