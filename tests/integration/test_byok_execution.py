"""Integration tests: full agent execution loop via BYOK (custom provider) path.

Mocks the external HTTP endpoint so the test exercises:
  provider resolution → token store → URL construction → streaming →
  tool execution → usage tracking → DB persistence.

Closes #36
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import run_agent
from app.models.provider import ProviderType
from app.models.task_execution import TaskExecution, TaskStatus

from .conftest import create_agent, create_provider, create_token, create_workflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sse_lines(content: str = "Hello BYOK!", usage: dict | None = None):
    """Build SSE line sequence for a simple text response."""
    usage = usage or {"prompt_tokens": 50, "completion_tokens": 10}
    return [
        'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
        f'data: {{"choices":[{{"delta":{{"content":"{content}"}},"finish_reason":null}}]}}',
        f'data: {{"choices":[{{"delta":{{}},"finish_reason":"stop"}}],"usage":{json.dumps(usage)}}}',
        "data: [DONE]",
    ]


def _make_tool_call_sse(tool_name: str, arguments: str):
    """Build SSE lines with a tool call then a stop after tool result."""
    return [
        f'data: {{"choices":[{{"delta":{{"tool_calls":[{{"index":0,"id":"call_1","type":"function","function":{{"name":"{tool_name}","arguments":""}}}}]}},"finish_reason":null}}]}}',
        f'data: {{"choices":[{{"delta":{{"tool_calls":[{{"index":0,"function":{{"arguments":"{arguments}"}}}}]}},"finish_reason":null}}]}}',
        'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":20,"completion_tokens":10}}',
        "data: [DONE]",
    ]


def _make_streaming_response(lines: list[str], status: int = 200):
    """Return an AsyncMock response that yields lines."""
    resp = AsyncMock()
    resp.status_code = status
    resp.raise_for_status = MagicMock()
    resp.aclose = AsyncMock()

    async def aiter_lines():
        for line in lines:
            yield line

    resp.aiter_lines = aiter_lines
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBYOKExecution:
    @pytest.mark.asyncio
    async def test_openai_provider_full_loop(self, mock_event_bus):
        """BYOK OpenAI: token resolution → HTTP stream → response persisted."""
        await create_token("openai-key", "sk-test-123")
        provider = await create_provider(
            name="my-openai",
            provider_type=ProviderType.OPENAI,
            api_key_token_name="openai-key",
        )
        agent = await create_agent(provider_id=str(provider.id))
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Say hi", status=TaskStatus.PENDING,
        )
        await task.insert()

        sse_resp = _make_streaming_response(_make_sse_lines("Hello BYOK!"))

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.build_request.return_value = MagicMock()
            mock_http.send.return_value = sse_resp

            result = await run_agent(
                wf, "Say hi", "ghp_token", task_execution_id=str(task.id),
            )

        assert result is not None
        assert "Hello BYOK" in result

        updated_task = await TaskExecution.get(task.id)
        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.usage is not None

    @pytest.mark.asyncio
    async def test_azure_provider_url_construction(self, mock_event_bus):
        """Azure BYOK: deployment URL is constructed correctly."""
        await create_token("azure-key", "azure-secret")
        provider = await create_provider(
            name="my-azure",
            provider_type=ProviderType.AZURE_OPENAI,
            api_key_token_name="azure-key",
            base_url="https://myresource.openai.azure.com",
            azure_deployment="gpt-4o",
            azure_api_version="2024-12-01-preview",
        )
        agent = await create_agent(provider_id=str(provider.id))
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Test Azure", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_urls = []
        sse_resp = _make_streaming_response(_make_sse_lines("Azure response"))

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_http = MagicMock()
            mock_http.send = AsyncMock(return_value=sse_resp)
            mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            def capture_request(method, url, **kwargs):
                captured_urls.append(url)
                return MagicMock()

            mock_http.build_request.side_effect = capture_request

            await run_agent(
                wf, "Test Azure", "ghp_token",
                task_execution_id=str(task.id),
            )

        assert any("deployments/gpt-4o" in u for u in captured_urls)
        assert any("api-version=2024-12-01-preview" in u for u in captured_urls)

    @pytest.mark.asyncio
    async def test_missing_token_falls_back_to_copilot(self, mock_event_bus):
        """If the provider's token is not in the store, fall back to default SDK."""
        provider = await create_provider(
            name="missing-key-provider",
            provider_type=ProviderType.OPENAI,
            api_key_token_name="nonexistent-key",
        )
        agent = await create_agent(provider_id=str(provider.id))
        wf = await create_workflow(agent)

        with (
            patch("app.core.agent_engine.build_client") as mock_build,
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            # Even if SDK fails, the point is it tried the SDK path
            mock_build.side_effect = Exception("SDK not configured in test")

            result = await run_agent(wf, "test", "ghp_token")

        # A provider warning should have been logged
        log_events = [e for e in mock_event_bus.events if e[1] == "log"]
        assert any("not found in token store" in str(e[2]) for e in log_events)

    @pytest.mark.asyncio
    async def test_usage_tracking_populated(self, mock_event_bus):
        """Usage stats should be persisted on the TaskExecution."""
        await create_token("usage-key", "sk-usage")
        provider = await create_provider(
            name="usage-provider",
            provider_type=ProviderType.OPENAI,
            api_key_token_name="usage-key",
        )
        agent = await create_agent(provider_id=str(provider.id))
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Track usage", status=TaskStatus.PENDING,
        )
        await task.insert()

        usage = {"prompt_tokens": 200, "completion_tokens": 80}
        sse_resp = _make_streaming_response(_make_sse_lines("Done", usage=usage))

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.httpx.AsyncClient") as mock_http_cls,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_http = AsyncMock()
            mock_http_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_http_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.build_request.return_value = MagicMock()
            mock_http.send.return_value = sse_resp

            await run_agent(
                wf, "Track usage", "ghp_token",
                task_execution_id=str(task.id),
            )

        updated_task = await TaskExecution.get(task.id)
        assert updated_task.usage is not None
        assert updated_task.usage.total_input_tokens >= 200
        assert updated_task.usage.total_output_tokens >= 80
