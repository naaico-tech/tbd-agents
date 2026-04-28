"""Unit tests for the Agent Chat feature (M7).

Tests cover:
- ChatSession / ChatMessage model construction
- Chat schemas
- Chat API endpoints (via FastAPI test client)
- handle_chat() async generator
- build_chat_context() context builder
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.schemas.chat import (
    ChatMessageResponse,
    ChatRequest,
    ChatSessionDetail,
    ChatSessionResponse,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_SESSION_ID = "6601a1b2c3d4e5f607890abd"
FAKE_MSG_ID = "6601a1b2c3d4e5f607890abe"


def _fake_agent():
    return SimpleNamespace(
        id=FAKE_ID,
        name="Deploy Bot",
        description="Handles deployments",
        system_prompt="You are a deployment assistant.",
        model="gpt-4.1",
        mcp_server_ids=[],
        mcp_server_tags=[],
        tool_definitions=[],
        builtin_tools=["bash"],
        custom_tool_ids=[],
        skill_ids=[],
        provider_id=None,
    )


def _fake_session(github_user="testuser"):
    from beanie import PydanticObjectId
    s = MagicMock(spec=ChatSession)
    s.id = PydanticObjectId(FAKE_SESSION_ID)
    s.agent_id = PydanticObjectId(FAKE_ID)
    s.github_user = github_user
    s.title = None
    s.message_count = 0
    s.created_at = datetime.now(UTC)
    s.updated_at = datetime.now(UTC)
    s.save = AsyncMock()
    s.insert = AsyncMock()
    s.delete = AsyncMock()
    return s


def _fake_message(role="user", content="Hello"):
    from beanie import PydanticObjectId
    m = MagicMock(spec=ChatMessage)
    m.id = PydanticObjectId(FAKE_MSG_ID)
    m.session_id = PydanticObjectId(FAKE_SESSION_ID)
    m.role = role
    m.content = content
    m.usage = None
    m.created_at = datetime.now(UTC)
    m.insert = AsyncMock()
    return m


# ── Model tests ───────────────────────────────────────────────────────────────


class TestChatSessionModel:
    def test_defaults(self):
        from beanie import PydanticObjectId
        s = ChatSession.model_construct(
            id=PydanticObjectId(FAKE_SESSION_ID),
            agent_id=PydanticObjectId(FAKE_ID),
            github_user="testuser",
        )
        assert s.message_count == 0
        assert s.title is None

    def test_settings(self):
        assert ChatSession.Settings.name == "chat_sessions"

    def test_collection_name(self):
        assert ChatSession.Settings.name == "chat_sessions"


class TestChatMessageModel:
    def test_user_message(self):
        from beanie import PydanticObjectId
        m = ChatMessage.model_construct(
            id=PydanticObjectId(FAKE_MSG_ID),
            session_id=PydanticObjectId(FAKE_SESSION_ID),
            role="user",
            content="What can you do?",
        )
        assert m.role == "user"
        assert m.content == "What can you do?"
        assert m.usage is None

    def test_assistant_message_with_usage(self):
        from beanie import PydanticObjectId
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        m = ChatMessage.model_construct(
            id=PydanticObjectId(FAKE_MSG_ID),
            session_id=PydanticObjectId(FAKE_SESSION_ID),
            role="assistant",
            content="I can help with deployments.",
            usage=usage,
        )
        assert m.role == "assistant"
        assert m.usage == usage

    def test_settings(self):
        assert ChatMessage.Settings.name == "chat_messages"


# ── Schema tests ──────────────────────────────────────────────────────────────


class TestChatSchemas:
    def test_chat_request_requires_message(self):
        req = ChatRequest(message="Hello")
        assert req.message == "Hello"
        assert req.session_id is None

    def test_chat_request_with_session_id(self):
        req = ChatRequest(message="Hello", session_id=FAKE_SESSION_ID)
        assert req.session_id == FAKE_SESSION_ID

    def test_chat_session_response(self):
        resp = ChatSessionResponse(
            id=FAKE_SESSION_ID,
            agent_id=FAKE_ID,
            title="First message",
            message_count=4,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        assert resp.id == FAKE_SESSION_ID
        assert resp.message_count == 4

    def test_chat_message_response(self):
        resp = ChatMessageResponse(
            id=FAKE_MSG_ID,
            role="user",
            content="Hello",
            usage=None,
            created_at=datetime.now(UTC),
        )
        assert resp.role == "user"

    def test_chat_session_detail_inherits_messages(self):
        detail = ChatSessionDetail(
            id=FAKE_SESSION_ID,
            agent_id=FAKE_ID,
            title=None,
            message_count=0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            messages=[],
        )
        assert detail.messages == []


# ── Chat handler tests ────────────────────────────────────────────────────────


class TestHandleChat:
    @pytest.mark.asyncio
    async def test_yields_session_event_first(self):
        """handle_chat always emits a session event as the first thing."""
        agent = _fake_agent()
        session = _fake_session()

        with (
            patch(
                "app.services.chat_handler.build_chat_context",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "app.services.chat_handler.chat_messages_total",
                MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock()))),
            ),
            patch(
                "app.services.chat_handler.chat_response_duration_seconds",
                MagicMock(labels=MagicMock(return_value=MagicMock(observe=MagicMock()))),
            ),
            patch(
                "app.services.chat_handler.httpx.AsyncClient",
            ) as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _make_stream_ctx(["data: [DONE]"])
            mock_client_cls.return_value = mock_client

            # Patch ChatMessage class: constructor returns fake instance,
            # find() returns empty history
            fake_msg_instance = MagicMock()
            fake_msg_instance.id = FAKE_MSG_ID
            fake_msg_instance.insert = AsyncMock()

            mock_chat_msg_cls = MagicMock(return_value=fake_msg_instance)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token="ghp_test",
                ):
                    events.append(ev)

        assert events[0]["type"] == "session"
        assert events[0]["session_id"] == str(session.id)

    @pytest.mark.asyncio
    async def test_yields_error_when_no_api_key(self):
        """handle_chat yields error event when no token and no provider."""
        agent = _fake_agent()
        session = _fake_session()

        from app.services.chat_handler import handle_chat

        events = []
        async for ev in handle_chat(
            agent=agent,
            session=session,
            user_message="Hello",
            github_user="testuser",
            github_token=None,  # no token
        ):
            events.append(ev)

        assert events[0]["type"] == "session"
        assert any(e["type"] == "error" for e in events)


# ── Chat context builder tests ────────────────────────────────────────────────


class TestBuildChatContext:
    @pytest.mark.asyncio
    async def test_includes_agent_profile(self):
        agent = _fake_agent()
        with (
            patch(
                "app.services.chat_context.Workflow.find",
                return_value=_fake_query([]),
            ),
            patch(
                "app.services.chat_context._memory_manager.build_memory_context",
                new=AsyncMock(return_value=""),
            ),
        ):
            from app.services.chat_context import build_chat_context
            context = await build_chat_context(agent, "testuser")

        assert "<agent_context>" in context
        assert "Deploy Bot" in context
        assert "gpt-4.1" in context

    @pytest.mark.asyncio
    async def test_includes_builtin_tools(self):
        agent = _fake_agent()
        with (
            patch(
                "app.services.chat_context.Workflow.find",
                return_value=_fake_query([]),
            ),
            patch(
                "app.services.chat_context._memory_manager.build_memory_context",
                new=AsyncMock(return_value=""),
            ),
        ):
            from app.services.chat_context import build_chat_context
            context = await build_chat_context(agent, "testuser")

        assert "bash" in context

    @pytest.mark.asyncio
    async def test_closes_agent_context_tag(self):
        agent = _fake_agent()
        with (
            patch(
                "app.services.chat_context.Workflow.find",
                return_value=_fake_query([]),
            ),
            patch(
                "app.services.chat_context._memory_manager.build_memory_context",
                new=AsyncMock(return_value=""),
            ),
        ):
            from app.services.chat_context import build_chat_context
            context = await build_chat_context(agent, "testuser")

        assert context.strip().endswith("</agent_context>")


# ── Chat API endpoint tests ───────────────────────────────────────────────────


class TestChatEndpoints:
    @pytest.mark.asyncio
    async def test_list_sessions_404_for_unknown_agent(self):
        from app.api.routes.chat import list_chat_sessions

        with patch(
            "app.api.routes.chat.Agent.get", new=AsyncMock(return_value=None)
        ):
            with pytest.raises(Exception) as exc_info:
                await list_chat_sessions(
                    agent_id=FAKE_ID,
                    skip=0,
                    limit=20,
                    user={"login": "testuser"},
                )
        from fastapi import HTTPException
        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_session_404_for_unknown_session(self):
        from app.api.routes.chat import get_chat_session

        agent = _fake_agent()
        with (
            patch("app.api.routes.chat.Agent.get", new=AsyncMock(return_value=agent)),
            patch("app.api.routes.chat.ChatSession.get", new=AsyncMock(return_value=None)),
        ):
            with pytest.raises(Exception) as exc_info:
                await get_chat_session(
                    agent_id=FAKE_ID,
                    session_id=FAKE_SESSION_ID,
                    user={"login": "testuser"},
                )
        from fastapi import HTTPException
        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_enforces_ownership(self):
        from app.api.routes.chat import delete_chat_session

        agent = _fake_agent()
        session = _fake_session(github_user="other_user")

        with (
            patch("app.api.routes.chat.Agent.get", new=AsyncMock(return_value=agent)),
            patch(
                "app.api.routes.chat.ChatSession.get",
                new=AsyncMock(return_value=session),
            ),
        ):
            with pytest.raises(Exception) as exc_info:
                await delete_chat_session(
                    agent_id=FAKE_ID,
                    session_id=FAKE_SESSION_ID,
                    user={"login": "testuser"},  # different from session owner
                )
        from fastapi import HTTPException
        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_sessions_returns_empty_list(self):
        from app.api.routes.chat import list_chat_sessions

        agent = _fake_agent()
        with (
            patch("app.api.routes.chat.Agent.get", new=AsyncMock(return_value=agent)),
            patch(
                "app.api.routes.chat.ChatSession.find",
                return_value=_fake_query([]),
            ),
        ):
            result = await list_chat_sessions(
                agent_id=FAKE_ID,
                skip=0,
                limit=20,
                user={"login": "testuser"},
            )
        assert result == []

    @pytest.mark.asyncio
    async def test_get_session_detail_returns_messages(self):
        from app.api.routes.chat import get_chat_session

        agent = _fake_agent()
        session = _fake_session()

        msg = _fake_message(role="user", content="What can you do?")

        with (
            patch("app.api.routes.chat.Agent.get", new=AsyncMock(return_value=agent)),
            patch(
                "app.api.routes.chat.ChatSession.get",
                new=AsyncMock(return_value=session),
            ),
            patch(
                "app.api.routes.chat.ChatMessage.find",
                return_value=_fake_query([msg]),
            ),
        ):
            result = await get_chat_session(
                agent_id=FAKE_ID,
                session_id=FAKE_SESSION_ID,
                user={"login": "testuser"},
            )

        assert len(result.messages) == 1
        assert result.messages[0].content == "What can you do?"


# ── URL resolution tests ──────────────────────────────────────────────────────


def _make_provider_mock(
    provider_type,
    base_url=None,
    azure_deployment=None,
    azure_api_version="2024-12-01-preview",
    name="test-provider",
):
    """Create a Provider-like mock for chat_handler tests."""
    from app.models.provider import Provider
    p = MagicMock(spec=Provider)
    p.name = name
    p.provider_type = provider_type
    p.api_key_token_name = "tok"
    p.base_url = base_url
    p.azure_deployment = azure_deployment
    p.azure_api_version = azure_api_version
    return p


class TestResolveUrl:
    def test_no_provider_uses_copilot_endpoint(self):
        """Default path must target api.githubcopilot.com, not GitHub Models.

        The GITHUB_TOKEN has 'copilot' scope, not 'models:read', so calling
        models.inference.ai.azure.com with it yields 401 Unauthorized.
        """
        from app.services.chat_handler import _resolve_url

        url = _resolve_url(None, "gpt-4.1")
        assert url.startswith("https://api.githubcopilot.com/"), (
            f"Default chat URL must use api.githubcopilot.com, got: {url}"
        )
        assert "models.inference.ai.azure.com" not in url

    def test_openai_provider_default_url(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(ProviderType.OPENAI)
        url = _resolve_url(p, "gpt-4o")
        assert url == "https://api.openai.com/v1/chat/completions"

    def test_openai_provider_custom_base_url(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(ProviderType.OPENAI, base_url="https://my-proxy.com/v1/")
        url = _resolve_url(p, "gpt-4o")
        assert url == "https://my-proxy.com/v1/chat/completions"

    def test_custom_provider_with_base_url(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(ProviderType.CUSTOM, base_url="https://openrouter.ai/api/v1")
        url = _resolve_url(p, "some-model")
        assert url == "https://openrouter.ai/api/v1/chat/completions"

    def test_custom_provider_no_base_url_raises(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(ProviderType.CUSTOM, base_url=None)
        with pytest.raises(ValueError, match="no base_url"):
            _resolve_url(p, "some-model")

    def test_azure_provider_without_deployment_in_base_url(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(
            ProviderType.AZURE_OPENAI,
            base_url="https://my-azure.openai.azure.com",
            azure_deployment="my-deployment",
            azure_api_version="2024-12-01-preview",
        )
        url = _resolve_url(p, "gpt-4o")
        assert "openai/deployments/my-deployment/chat/completions" in url
        assert "api-version=2024-12-01-preview" in url

    def test_azure_provider_deployment_falls_back_to_model(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(
            ProviderType.AZURE_OPENAI,
            base_url="https://my-azure.openai.azure.com",
            azure_deployment=None,
        )
        url = _resolve_url(p, "gpt-4o")
        assert "openai/deployments/gpt-4o/chat/completions" in url

    def test_azure_provider_with_deployment_already_in_base_url(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(
            ProviderType.AZURE_OPENAI,
            base_url="https://my-azure.openai.azure.com/openai/deployments/my-dep",
            azure_api_version="2024-12-01-preview",
        )
        url = _resolve_url(p, "gpt-4o")
        assert url.endswith("/chat/completions?api-version=2024-12-01-preview")
        assert "openai/deployments" in url

    def test_anthropic_provider_raises_value_error(self):
        """Anthropic is not supported in chat mode — no OpenAI-compatible endpoint."""
        from app.models.provider import ProviderType
        from app.services.chat_handler import _resolve_url

        p = _make_provider_mock(ProviderType.ANTHROPIC)
        with pytest.raises(ValueError, match="Anthropic"):
            _resolve_url(p, "claude-3")


# ── BYOK header building tests ────────────────────────────────────────────────


class TestBuildHeaders:
    def test_no_provider_uses_bearer_auth(self):
        from app.services.chat_handler import _build_headers

        hdrs = _build_headers(None, "ghp_mytoken")
        assert hdrs["Authorization"] == "Bearer ghp_mytoken"
        assert hdrs["content-type"] == "application/json"

    def test_openai_provider_uses_bearer_auth(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _build_headers

        p = _make_provider_mock(ProviderType.OPENAI)
        hdrs = _build_headers(p, "sk-mykey")
        assert hdrs["Authorization"] == "Bearer sk-mykey"
        assert hdrs["content-type"] == "application/json"

    def test_azure_provider_uses_api_key_header(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _build_headers

        p = _make_provider_mock(ProviderType.AZURE_OPENAI)
        hdrs = _build_headers(p, "azure-secret")
        assert hdrs["api-key"] == "azure-secret"
        assert "Authorization" not in hdrs
        assert hdrs["content-type"] == "application/json"

    def test_anthropic_provider_uses_x_api_key(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _build_headers

        p = _make_provider_mock(ProviderType.ANTHROPIC)
        hdrs = _build_headers(p, "ant-mykey")
        assert hdrs["x-api-key"] == "ant-mykey"
        assert "anthropic-version" in hdrs
        assert "Authorization" not in hdrs

    def test_custom_provider_uses_bearer_auth(self):
        from app.models.provider import ProviderType
        from app.services.chat_handler import _build_headers

        p = _make_provider_mock(ProviderType.CUSTOM, base_url="https://openrouter.ai/api/v1")
        hdrs = _build_headers(p, "or-key")
        assert hdrs["Authorization"] == "Bearer or-key"
        assert hdrs["content-type"] == "application/json"


# ── BYOK handle_chat integration tests ───────────────────────────────────────


class TestHandleChatByok:
    @pytest.mark.asyncio
    async def test_byok_openai_provider_uses_provider_url_and_key(self):
        """handle_chat with OpenAI BYOK provider calls provider URL with stored key."""
        from app.models.provider import ProviderType
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="BYOK Bot",
            description="",
            system_prompt="You are helpful.",
            model="gpt-4o",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()
        provider = _make_provider_mock(
            ProviderType.OPENAI, base_url="https://api.openai.com/v1"
        )

        captured_url = []
        captured_auth = []

        def _mock_stream(method, url, headers, json):
            captured_url.append(url)
            captured_auth.append(headers.get("Authorization", ""))
            return _make_stream_ctx(["data: [DONE]"])()

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.chat_response_duration_seconds", MagicMock(labels=MagicMock(return_value=MagicMock(observe=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.token_manager") as mock_tm,
            patch("app.services.chat_handler.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_prov_cls.get = AsyncMock(return_value=provider)
            mock_tm.get_token_value = AsyncMock(return_value="sk-openai-key")

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _mock_stream
            mock_client_cls.return_value = mock_client

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token=None,
                ):
                    events.append(ev)

        assert captured_url[0] == "https://api.openai.com/v1/chat/completions"
        assert captured_auth[0] == "Bearer sk-openai-key"
        assert any(e["type"] == "done" for e in events)

    @pytest.mark.asyncio
    async def test_byok_github_copilot_provider_uses_copilot_endpoint(self):
        """handle_chat with github_copilot BYOK uses api.githubcopilot.com with stored token."""
        from app.models.provider import ProviderType
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="Copilot Bot",
            description="",
            system_prompt="You are helpful.",
            model="gpt-4.1",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()
        provider = _make_provider_mock(ProviderType.GITHUB_COPILOT)

        captured_url = []
        captured_auth = []

        def _mock_stream(method, url, headers, json):
            captured_url.append(url)
            captured_auth.append(headers.get("Authorization", ""))
            return _make_stream_ctx(["data: [DONE]"])()

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.chat_response_duration_seconds", MagicMock(labels=MagicMock(return_value=MagicMock(observe=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.token_manager") as mock_tm,
            patch("app.services.chat_handler.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_prov_cls.get = AsyncMock(return_value=provider)
            mock_tm.get_token_value = AsyncMock(return_value="ghp_stored_token")

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _mock_stream
            mock_client_cls.return_value = mock_client

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token=None,
                ):
                    events.append(ev)

        assert "api.githubcopilot.com" in captured_url[0]
        assert captured_auth[0] == "Bearer ghp_stored_token"

    @pytest.mark.asyncio
    async def test_byok_anthropic_provider_yields_error_event(self):
        """handle_chat with Anthropic BYOK yields error — not OpenAI-compatible."""
        from app.models.provider import ProviderType
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="Ant Bot",
            description="",
            system_prompt="You are helpful.",
            model="claude-3",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()
        provider = _make_provider_mock(ProviderType.ANTHROPIC)

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.token_manager") as mock_tm,
        ):
            mock_prov_cls.get = AsyncMock(return_value=provider)
            mock_tm.get_token_value = AsyncMock(return_value="ant-key")

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token=None,
                ):
                    events.append(ev)

        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, "Expected an error event for Anthropic BYOK in chat mode"
        assert "Anthropic" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_byok_provider_resolution_failure_falls_back_to_github_token(self):
        """When Provider.get() raises, handle_chat falls back to github_token."""
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="Fallback Bot",
            description="",
            system_prompt="You are helpful.",
            model="gpt-4.1",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()

        captured_auth = []

        def _mock_stream(method, url, headers, json):
            captured_auth.append(headers.get("Authorization", ""))
            return _make_stream_ctx(["data: [DONE]"])()

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.chat_response_duration_seconds", MagicMock(labels=MagicMock(return_value=MagicMock(observe=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_prov_cls.get = AsyncMock(side_effect=Exception("DB connection error"))

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _mock_stream
            mock_client_cls.return_value = mock_client

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token="ghp_fallback_token",
                ):
                    events.append(ev)

        assert captured_auth[0] == "Bearer ghp_fallback_token"
        assert any(e["type"] == "done" for e in events)

    @pytest.mark.asyncio
    async def test_byok_token_resolution_returns_none_falls_back_to_github_token(self):
        """When token_manager returns None for the provider key, fall back to github_token."""
        from app.models.provider import ProviderType
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="Fallback Bot",
            description="",
            system_prompt="You are helpful.",
            model="gpt-4.1",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()
        provider = _make_provider_mock(ProviderType.OPENAI, base_url="https://api.openai.com/v1")

        captured_auth = []

        def _mock_stream(method, url, headers, json):
            captured_auth.append(headers.get("Authorization", ""))
            return _make_stream_ctx(["data: [DONE]"])()

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.chat_response_duration_seconds", MagicMock(labels=MagicMock(return_value=MagicMock(observe=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.token_manager") as mock_tm,
            patch("app.services.chat_handler.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_prov_cls.get = AsyncMock(return_value=provider)
            mock_tm.get_token_value = AsyncMock(return_value=None)  # token not found

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _mock_stream
            mock_client_cls.return_value = mock_client

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token="ghp_fallback_token",
                ):
                    events.append(ev)

        assert captured_auth[0] == "Bearer ghp_fallback_token"
        assert any(e["type"] == "done" for e in events)

    @pytest.mark.asyncio
    async def test_byok_http_error_logs_response_body_and_yields_error(self):
        """When LLM returns non-2xx, handler logs response body and yields error event."""
        from app.models.provider import ProviderType
        from types import SimpleNamespace

        agent = SimpleNamespace(
            id=FAKE_ID,
            name="BYOK Bot",
            description="",
            system_prompt="You are helpful.",
            model="gpt-4o",
            mcp_server_ids=[],
            mcp_server_tags=[],
            tool_definitions=[],
            builtin_tools=[],
            custom_tool_ids=[],
            skill_ids=[],
            provider_id=FAKE_ID,
        )
        session = _fake_session()
        provider = _make_provider_mock(ProviderType.OPENAI, base_url="https://api.openai.com/v1")

        def _mock_error_stream(method, url, headers, json):
            resp = AsyncMock()
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            resp.status_code = 400
            resp.aread = AsyncMock(return_value=b'{"error": "bad request"}')

            def _ctx():
                return resp

            return _ctx()

        with (
            patch("app.services.chat_handler.build_chat_context", new=AsyncMock(return_value="")),
            patch("app.services.chat_handler.chat_messages_total", MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock())))),
            patch("app.services.chat_handler.Provider") as mock_prov_cls,
            patch("app.services.chat_handler.token_manager") as mock_tm,
            patch("app.services.chat_handler.httpx.AsyncClient") as mock_client_cls,
        ):
            mock_prov_cls.get = AsyncMock(return_value=provider)
            mock_tm.get_token_value = AsyncMock(return_value="sk-openai-key")

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.stream = _mock_error_stream
            mock_client_cls.return_value = mock_client

            fake_msg = MagicMock()
            fake_msg.id = FAKE_MSG_ID
            fake_msg.insert = AsyncMock()
            mock_chat_msg_cls = MagicMock(return_value=fake_msg)
            mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

            with patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls):
                from app.services.chat_handler import handle_chat
                events = []
                async for ev in handle_chat(
                    agent=agent,
                    session=session,
                    user_message="Hello",
                    github_user="testuser",
                    github_token=None,
                ):
                    events.append(ev)

        error_events = [e for e in events if e["type"] == "error"]
        assert error_events, "Expected error event when LLM returns 400"
        assert error_events[0]["message"] == "LLM request failed. Please try again."


# ── SSE format tests ──────────────────────────────────────────────────────────


class TestChatSSEFormat:
    def test_session_event_format(self):
        from app.services.chat_handler import _session_event
        ev = _session_event("abc123")
        assert ev["type"] == "session"
        assert ev["session_id"] == "abc123"

    def test_delta_event_format(self):
        from app.services.chat_handler import _delta_event
        ev = _delta_event("hello")
        assert ev["type"] == "delta"
        assert ev["content"] == "hello"

    def test_done_event_format(self):
        from app.services.chat_handler import _done_event
        usage = {"prompt_tokens": 10, "completion_tokens": 5}
        ev = _done_event(usage, "msg123")
        assert ev["type"] == "done"
        assert ev["usage"] == usage
        assert ev["message_id"] == "msg123"

    def test_error_event_format(self):
        from app.services.chat_handler import _error_event
        ev = _error_event("something went wrong")
        assert ev["type"] == "error"
        assert ev["message"] == "something went wrong"


# ── Helpers ───────────────────────────────────────────────────────────────────


def aiter_from_list(items):
    """Return an async iterator from a list of items."""
    async def _iter():
        for item in items:
            yield item
    return _iter()


def _fake_query(results):
    """Return a chainable mock for Beanie find() queries."""
    q = MagicMock()
    q.sort = MagicMock(return_value=q)
    q.skip = MagicMock(return_value=q)
    q.limit = MagicMock(return_value=q)
    q.to_list = AsyncMock(return_value=results)
    q.delete = AsyncMock()
    return q


def _make_stream_ctx(lines, status_code: int = 200):
    """Return a mock async context manager for httpx client.stream()."""
    resp = AsyncMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.aiter_lines = MagicMock(return_value=aiter_from_list(lines))

    def _stream(*args, **kwargs):
        return resp

    return _stream
