"""Tests for BYOK (Bring Your Own Key) custom provider features.

Covers: Azure URL routing, retry logic, context compaction, streaming,
header building, and provider URL resolution.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.agent_engine import (
    _build_provider_headers,
    _compact_messages,
    _http_post_with_retry,
    _resolve_provider_url,
    _stream_chat_completion,
)
from app.models.provider import Provider, ProviderType


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_provider(
    provider_type: ProviderType = ProviderType.OPENAI,
    base_url: str | None = None,
    azure_deployment: str | None = None,
    azure_api_version: str = "2024-12-01-preview",
    name: str = "test-provider",
) -> MagicMock:
    """Create a Provider-like mock without database interaction."""
    p = MagicMock(spec=Provider)
    p.name = name
    p.provider_type = provider_type
    p.api_key_token_name = "tok"
    p.base_url = base_url
    p.azure_deployment = azure_deployment
    p.azure_api_version = azure_api_version
    return p


# ── _resolve_provider_url ───────────────────────────────────────────────────


class TestResolveProviderUrl:
    def test_openai_default_url(self):
        p = _make_provider(ProviderType.OPENAI)
        assert _resolve_provider_url(p) == "https://api.openai.com/v1/chat/completions"

    def test_openai_custom_base(self):
        p = _make_provider(ProviderType.OPENAI, base_url="https://my-proxy.com/v1/")
        assert _resolve_provider_url(p) == "https://my-proxy.com/v1/chat/completions"

    def test_azure_with_deployment(self):
        p = _make_provider(
            ProviderType.AZURE_OPENAI,
            base_url="https://myinstance.openai.azure.com",
            azure_deployment="gpt-4o",
            azure_api_version="2024-12-01-preview",
        )
        url = _resolve_provider_url(p, model="gpt-4o")
        assert url == (
            "https://myinstance.openai.azure.com/openai/deployments/gpt-4o"
            "/chat/completions?api-version=2024-12-01-preview"
        )

    def test_azure_deployment_fallback_to_model(self):
        p = _make_provider(
            ProviderType.AZURE_OPENAI,
            base_url="https://myinstance.openai.azure.com",
        )
        url = _resolve_provider_url(p, model="gpt-35-turbo")
        assert "/deployments/gpt-35-turbo/" in url

    def test_azure_no_deployment_or_model_raises(self):
        p = _make_provider(
            ProviderType.AZURE_OPENAI,
            base_url="https://myinstance.openai.azure.com",
        )
        with pytest.raises(ValueError, match="requires a deployment name"):
            _resolve_provider_url(p, model="")

    def test_no_base_url_and_no_default_raises(self):
        p = _make_provider(ProviderType.CUSTOM)
        with pytest.raises(ValueError, match="no base_url configured"):
            _resolve_provider_url(p)

    def test_anthropic_default_url(self):
        p = _make_provider(ProviderType.ANTHROPIC)
        assert _resolve_provider_url(p) == "https://api.anthropic.com/v1/chat/completions"


# ── _build_provider_headers ──────────────────────────────────────────────────


class TestBuildProviderHeaders:
    def test_openai_headers(self):
        p = _make_provider(ProviderType.OPENAI)
        h = _build_provider_headers(p, "sk-test")
        assert h["Authorization"] == "Bearer sk-test"
        assert h["content-type"] == "application/json"

    def test_anthropic_headers(self):
        p = _make_provider(ProviderType.ANTHROPIC)
        h = _build_provider_headers(p, "sk-ant-test")
        assert h["x-api-key"] == "sk-ant-test"
        assert "anthropic-version" in h

    def test_azure_headers(self):
        p = _make_provider(ProviderType.AZURE_OPENAI)
        h = _build_provider_headers(p, "azure-key")
        assert h["api-key"] == "azure-key"


# ── _compact_messages ────────────────────────────────────────────────────────


class TestCompactMessages:
    def test_small_list_unchanged(self):
        msgs = [
            {"role": "system", "content": "You are a helper."},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = _compact_messages(msgs, "hi")
        assert result == msgs

    def test_compacts_large_list(self):
        msgs = [{"role": "system", "content": "sys"}]
        msgs.append({"role": "user", "content": "original question"})
        # Add 20 intermediate messages
        for i in range(20):
            msgs.append({"role": "assistant", "content": f"thought {i}"})
            msgs.append({"role": "tool", "tool_call_id": f"tc_{i}", "content": f"result {i}"})
        # Total: 1 system + 1 user + 40 assistant/tool = 42

        result = _compact_messages(msgs, "original question")

        # Should have: system + first user + compaction note + last 6
        assert len(result) == 9  # 1 + 1 + 1 + 6
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"
        assert result[2]["role"] == "system"  # compaction note
        assert "compacted" in result[2]["content"].lower()
        assert result[-1] == msgs[-1]

    def test_keeps_8_or_fewer_unchanged(self):
        msgs = [{"role": "system", "content": "sys"}]
        for i in range(7):
            msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": str(i)})
        assert len(msgs) == 8
        result = _compact_messages(msgs, "0")
        assert result == msgs

    def test_compaction_note_contains_count(self):
        msgs = [{"role": "system", "content": "sys"}]
        msgs.append({"role": "user", "content": "q"})
        for i in range(10):
            msgs.append({"role": "assistant", "content": f"a{i}"})
        # 12 messages total, 2 head + 6 tail = 8, dropped = 4
        result = _compact_messages(msgs, "q")
        note = [m for m in result if "compacted" in m.get("content", "").lower()]
        assert len(note) == 1
        assert "4" in note[0]["content"]


# ── _http_post_with_retry ───────────────────────────────────────────────────


class TestHttpPostWithRetry:
    @pytest.mark.asyncio
    async def test_success_first_try(self):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = mock_resp
        mock_resp.raise_for_status = MagicMock()

        result = await _http_post_with_retry(client, "http://test", {}, {})
        assert result == mock_resp
        assert client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_429(self):
        rate_limit_resp = MagicMock(spec=httpx.Response)
        rate_limit_resp.status_code = 429
        rate_limit_resp.headers = {"Retry-After": "0.01"}

        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = [rate_limit_resp, ok_resp]

        with patch("app.core.agent_engine.asyncio.sleep", new_callable=AsyncMock):
            result = await _http_post_with_retry(client, "http://test", {}, {}, max_retries=2)

        assert result == ok_resp
        assert client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_connect_error(self):
        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = [httpx.ConnectError("fail"), ok_resp]

        with patch("app.core.agent_engine.asyncio.sleep", new_callable=AsyncMock):
            result = await _http_post_with_retry(client, "http://test", {}, {}, max_retries=2)

        assert result == ok_resp

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self):
        resp_500 = MagicMock(spec=httpx.Response)
        resp_500.status_code = 500
        resp_500.headers = {}

        def raise_status():
            raise httpx.HTTPStatusError("500", request=MagicMock(), response=resp_500)

        resp_500.raise_for_status = raise_status

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.return_value = resp_500

        with patch("app.core.agent_engine.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(httpx.HTTPStatusError):
                await _http_post_with_retry(client, "http://test", {}, {}, max_retries=2)

    @pytest.mark.asyncio
    async def test_respects_retry_after_header(self):
        rate_limit_resp = MagicMock(spec=httpx.Response)
        rate_limit_resp.status_code = 429
        rate_limit_resp.headers = {"Retry-After": "2.5"}

        ok_resp = MagicMock(spec=httpx.Response)
        ok_resp.status_code = 200
        ok_resp.raise_for_status = MagicMock()

        client = AsyncMock(spec=httpx.AsyncClient)
        client.post.side_effect = [rate_limit_resp, ok_resp]

        sleep_mock = AsyncMock()
        with patch("app.core.agent_engine.asyncio.sleep", sleep_mock):
            await _http_post_with_retry(client, "http://test", {}, {}, max_retries=2)

        # Should have slept with the Retry-After value
        sleep_mock.assert_called_once_with(2.5)


# ── _stream_chat_completion ──────────────────────────────────────────────────


class TestStreamChatCompletion:
    @pytest.mark.asyncio
    async def test_streams_content_deltas(self):
        """Test that content deltas are accumulated and published."""
        lines = [
            'data: {"choices":[{"delta":{"role":"assistant"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"Hello"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":" world"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":5}}',
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.aclose = AsyncMock()

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines

        client = AsyncMock(spec=httpx.AsyncClient)
        client.build_request.return_value = MagicMock()
        client.send.return_value = mock_response

        with patch("app.core.agent_engine.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await _stream_chat_completion(
                client, "http://test", {}, {"model": "gpt-4"}, "wf-123",
            )

        assert result["choices"][0]["message"]["content"] == "Hello world"
        assert result["choices"][0]["finish_reason"] == "stop"
        assert result["usage"]["prompt_tokens"] == 10

    @pytest.mark.asyncio
    async def test_streams_tool_calls(self):
        """Test that tool call deltas are assembled correctly."""
        lines = [
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_weather","arguments":""}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"city\\":"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"\\"NYC\\"}"}}]},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":20,"completion_tokens":15}}',
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.aclose = AsyncMock()

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines

        client = AsyncMock(spec=httpx.AsyncClient)
        client.build_request.return_value = MagicMock()
        client.send.return_value = mock_response

        with patch("app.core.agent_engine.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            result = await _stream_chat_completion(
                client, "http://test", {}, {"model": "gpt-4"}, "wf-123",
            )

        tool_calls = result["choices"][0]["message"]["tool_calls"]
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call_1"
        assert tool_calls[0]["function"]["name"] == "get_weather"
        assert json.loads(tool_calls[0]["function"]["arguments"]) == {"city": "NYC"}

    @pytest.mark.asyncio
    async def test_publishes_deltas_via_event_bus(self):
        """Test that content deltas are published to the event bus."""
        lines = [
            'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{"content":"!"},"finish_reason":null}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.aclose = AsyncMock()

        async def aiter_lines():
            for line in lines:
                yield line

        mock_response.aiter_lines = aiter_lines

        client = AsyncMock(spec=httpx.AsyncClient)
        client.build_request.return_value = MagicMock()
        client.send.return_value = mock_response

        publish_calls = []

        async def fake_publish(wf_id, event_type, data):
            publish_calls.append((wf_id, event_type, data))

        with patch("app.core.agent_engine.event_bus") as mock_bus:
            mock_bus.publish = fake_publish
            await _stream_chat_completion(
                client, "http://test", {}, {"model": "gpt-4"}, "wf-123",
            )

        # Wait for any scheduled tasks
        await asyncio.sleep(0.05)

        # Should have published two deltas
        delta_calls = [c for c in publish_calls if c[1] == "message_delta"]
        assert len(delta_calls) == 2
        assert delta_calls[0][2]["delta"] == "Hi"
        assert delta_calls[1][2]["delta"] == "!"
