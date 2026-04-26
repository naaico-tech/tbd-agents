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
from app.models.provider import ProviderType
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

    @pytest.mark.asyncio
    async def test_google_adk_provider_requires_stored_token(self):
        agent = _fake_agent()
        agent.provider_id = "6601a1b2c3d4e5f607890abf"
        session = _fake_session()
        provider = SimpleNamespace(
            name="google-adk",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="missing-gemini-token",
        )

        from app.services.chat_handler import handle_chat

        with (
            patch("app.services.chat_handler.Provider.get", new=AsyncMock(return_value=provider)),
            patch(
                "app.services.chat_handler.token_manager.get_token_value",
                new=AsyncMock(return_value=None),
            ),
        ):
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
        assert events[1] == {
            "type": "error",
            "message": (
                "Google ADK provider 'google-adk' requires a stored Gemini API key "
                "in token 'missing-gemini-token'."
            ),
        }

    @pytest.mark.asyncio
    async def test_google_adk_vertex_provider_allows_missing_stored_token(self):
        agent = _fake_agent()
        agent.provider_id = "6601a1b2c3d4e5f607890ac0"
        agent.model = "gemini-2.5-flash"
        session = _fake_session()
        provider = SimpleNamespace(
            name="google-adk-vertex",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="missing-gemini-token",
            google_use_vertex_ai=True,
            google_cloud_project="my-project",
            google_cloud_location="us-central1",
            base_url=None,
        )
        user_msg_instance = MagicMock()
        user_msg_instance.id = FAKE_MSG_ID
        user_msg_instance.insert = AsyncMock()
        assistant_msg_instance = MagicMock()
        assistant_msg_instance.id = FAKE_MSG_ID
        assistant_msg_instance.insert = AsyncMock()
        mock_chat_msg_cls = MagicMock(side_effect=[user_msg_instance, assistant_msg_instance])
        mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

        chunks = [
            SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[SimpleNamespace(text="Hello Vertex", thought=False)]
                        )
                    )
                ],
                usage_metadata=None,
            )
        ]
        fake_client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    generate_content_stream=AsyncMock(return_value=aiter_from_list(chunks))
                ),
                aclose=AsyncMock(),
            ),
            close=MagicMock(),
        )

        with (
            patch(
                "app.services.chat_handler.build_chat_context",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "app.services.chat_handler.Provider.get",
                new=AsyncMock(return_value=provider),
            ),
            patch(
                "app.services.chat_handler.token_manager.get_token_value",
                new=AsyncMock(return_value=None),
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
                "app.services.chat_handler.build_google_adk_client",
                return_value=fake_client,
            ) as mock_build_client,
            patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls),
        ):
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
        assert events[1] == {"type": "delta", "content": "Hello Vertex"}
        assert events[2]["type"] == "done"
        runtime_config = mock_build_client.call_args.args[0]
        assert runtime_config["api_key"] is None
        assert runtime_config["use_vertex_ai"] is True

    @pytest.mark.asyncio
    async def test_google_adk_provider_streams_chat_response(self):
        agent = _fake_agent()
        agent.provider_id = "6601a1b2c3d4e5f607890ac0"
        agent.model = "gemini-2.5-flash"
        session = _fake_session()
        provider = SimpleNamespace(
            name="google-adk",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-token",
            google_use_vertex_ai=False,
            google_cloud_project=None,
            google_cloud_location=None,
            base_url=None,
        )
        user_msg_instance = MagicMock()
        user_msg_instance.id = FAKE_MSG_ID
        user_msg_instance.insert = AsyncMock()
        assistant_msg_instance = MagicMock()
        assistant_msg_instance.id = FAKE_MSG_ID
        assistant_msg_instance.insert = AsyncMock()
        mock_chat_msg_cls = MagicMock(side_effect=[user_msg_instance, assistant_msg_instance])
        mock_chat_msg_cls.find = MagicMock(return_value=_fake_query([]))

        chunks = [
            SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[SimpleNamespace(text="Hello", thought=False)]
                        )
                    )
                ],
                usage_metadata=None,
            ),
            SimpleNamespace(
                candidates=[
                    SimpleNamespace(
                        content=SimpleNamespace(
                            parts=[SimpleNamespace(text=" world", thought=False)]
                        )
                    )
                ],
                usage_metadata=SimpleNamespace(
                    prompt_token_count=12,
                    tool_use_prompt_token_count=0,
                    candidates_token_count=4,
                    cached_content_token_count=2,
                ),
            ),
        ]
        fake_client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    generate_content_stream=AsyncMock(return_value=aiter_from_list(chunks))
                ),
                aclose=AsyncMock(),
            ),
            close=MagicMock(),
        )

        with (
            patch(
                "app.services.chat_handler.build_chat_context",
                new=AsyncMock(return_value=""),
            ),
            patch(
                "app.services.chat_handler.Provider.get",
                new=AsyncMock(return_value=provider),
            ),
            patch(
                "app.services.chat_handler.token_manager.get_token_value",
                new=AsyncMock(return_value="gemini-secret"),
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
                "app.services.chat_handler.build_google_adk_client",
                return_value=fake_client,
            ),
            patch("app.services.chat_handler.ChatMessage", mock_chat_msg_cls),
        ):
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

        assert events[0]["type"] == "session"
        assert events[1] == {"type": "delta", "content": "Hello"}
        assert events[2] == {"type": "delta", "content": " world"}
        assert events[3] == {
            "type": "done",
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 4,
                "total_tokens": 16,
                "cached_tokens": 2,
            },
            "message_id": FAKE_MSG_ID,
        }
        fake_client.aio.models.generate_content_stream.assert_awaited_once()
        fake_client.aio.aclose.assert_awaited_once()
        fake_client.close.assert_called_once()


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

        with patch("app.api.routes.chat.Agent.get", new=AsyncMock(return_value=None)):
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


def _make_stream_ctx(lines):
    """Return a mock async context manager for httpx client.stream()."""
    resp = AsyncMock()
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    resp.raise_for_status = MagicMock()
    resp.aiter_lines = MagicMock(return_value=aiter_from_list(lines))

    def _stream(*args, **kwargs):
        return resp

    return _stream
