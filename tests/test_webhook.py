"""Tests for webhook dispatch after task completion."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import httpx
import pytest

from app.core.agent_engine import _classify_error, _fire_error_webhook, _fire_webhook


def _make_httpx_response(status: int = 200) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("GET", "http://example.com"))



class TestFireWebhook:
    """Unit tests for the _fire_webhook helper."""

    @pytest.mark.asyncio
    async def test_successful_webhook_post(self):
        """_fire_webhook POSTs the payload to the URL and logs the status code."""
        payload = {"task_id": "abc", "status": "completed"}
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.agent_engine.httpx.AsyncClient", return_value=mock_client):
            await _fire_webhook("https://example.com/hook", payload)

        mock_client.post.assert_called_once_with(
            "https://example.com/hook",
            json=payload,
            headers={"Content-Type": "application/json"},
        )

    @pytest.mark.asyncio
    async def test_webhook_failure_does_not_raise(self):
        """_fire_webhook swallows exceptions so task completion is unaffected."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.agent_engine.httpx.AsyncClient", return_value=mock_client):
            # Should not raise
            await _fire_webhook("https://bad-host.invalid/hook", {"status": "completed"})

    @pytest.mark.asyncio
    async def test_webhook_payload_structure(self):
        """_fire_webhook forwards the full payload dict as JSON."""
        now = datetime.now(UTC)
        payload = {
            "task_id": "task-123",
            "workflow_id": "wf-456",
            "workflow_title": "My Workflow",
            "prompt": "Do something",
            "response": "Done",
            "status": "completed",
            "elapsed_seconds": 3.14,
            "timestamp": now.isoformat(),
        }

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.agent_engine.httpx.AsyncClient", return_value=mock_client):
            await _fire_webhook("https://example.com/hook", payload)

        _, call_kwargs = mock_client.post.call_args
        assert call_kwargs["json"] == payload

    @pytest.mark.asyncio
    async def test_webhook_timeout_uses_10_seconds(self):
        """AsyncClient is created with a 10-second timeout."""
        mock_response = MagicMock()
        mock_response.status_code = 204

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_constructor = MagicMock(return_value=mock_client)

        with patch("app.core.agent_engine.httpx.AsyncClient", mock_constructor):
            await _fire_webhook("https://example.com/hook", {})

        mock_constructor.assert_called_once_with(timeout=10)


class TestWorkflowWebhookField:
    """Tests for webhook_url field on Workflow model and schemas."""

    def test_workflow_model_has_webhook_url(self):
        """Workflow document has an optional webhook_url field."""
        from app.models.workflow import Workflow

        fields = Workflow.model_fields
        assert "webhook_url" in fields
        # Default is None
        assert fields["webhook_url"].default is None

    def test_workflow_create_schema_has_webhook_url(self):
        """WorkflowCreate schema accepts webhook_url."""
        from app.schemas.workflow import WorkflowCreate

        schema = WorkflowCreate(agent_id="abc123", webhook_url="https://example.com/hook")
        assert schema.webhook_url == "https://example.com/hook"

    def test_workflow_create_schema_webhook_url_optional(self):
        """WorkflowCreate schema works without webhook_url."""
        from app.schemas.workflow import WorkflowCreate

        schema = WorkflowCreate(agent_id="abc123")
        assert schema.webhook_url is None

    def test_workflow_update_schema_has_webhook_url(self):
        """WorkflowUpdate schema accepts webhook_url."""
        from app.schemas.workflow import WorkflowUpdate

        schema = WorkflowUpdate(webhook_url="https://example.com/hook")
        assert schema.webhook_url == "https://example.com/hook"

    def test_workflow_response_schema_has_webhook_url(self):
        """WorkflowResponse schema includes webhook_url field."""
        from app.schemas.workflow import WorkflowResponse

        fields = WorkflowResponse.model_fields
        assert "webhook_url" in fields


class TestClassifyError:
    """Unit tests for _classify_error()."""

    def test_rate_limit_error(self):
        """anthropic.RateLimitError → rate_limit_exceeded with status 429."""
        exc = anthropic.RateLimitError(
            "rate limited", response=_make_httpx_response(429), body=None
        )
        error_type, msg, code = _classify_error(exc)
        assert error_type == "rate_limit_exceeded"
        assert code == 429
        assert "rate limited" in msg

    def test_connect_error(self):
        """httpx.ConnectError → connection_error with no status code."""
        exc = httpx.ConnectError("connection refused")
        error_type, msg, code = _classify_error(exc)
        assert error_type == "connection_error"
        assert code is None

    def test_timeout_error(self):
        """httpx.ReadTimeout → timeout_error with no status code."""
        exc = httpx.ReadTimeout("read timed out")
        error_type, msg, code = _classify_error(exc)
        assert error_type == "timeout_error"
        assert code is None

    def test_http_status_error(self):
        """httpx.HTTPStatusError with status 500 → http_error with status code 500."""
        req = httpx.Request("GET", "http://example.com")
        resp = httpx.Response(500, request=req, text="server error")
        exc = httpx.HTTPStatusError("error", request=req, response=resp)
        error_type, msg, code = _classify_error(exc)
        assert error_type == "http_error"
        assert code == 500
        assert "500" in msg

    def test_generic_error(self):
        """RuntimeError → internal_error with no status code."""
        exc = RuntimeError("something unexpected")
        error_type, msg, code = _classify_error(exc)
        assert error_type == "internal_error"
        assert code is None
        assert "something unexpected" in msg


class TestFireErrorWebhook:
    """Unit tests for _fire_error_webhook()."""

    @pytest.mark.asyncio
    async def test_no_call_when_url_is_none(self):
        """When error_webhook_url is None, _fire_webhook is not called."""
        workflow = MagicMock()
        workflow.error_webhook_url = None

        with patch("app.core.agent_engine._fire_webhook") as mock_fire:
            await _fire_error_webhook(workflow, RuntimeError("oops"), None, "test prompt")

        mock_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_fires_with_structured_payload(self):
        """When error_webhook_url is set, _fire_webhook is called with a structured payload."""
        workflow = MagicMock()
        workflow.error_webhook_url = "https://example.com/error-hook"
        workflow.id = "wf-123"
        workflow.title = "Test Workflow"

        exc = RuntimeError("boom")

        captured = {}

        async def fake_fire_webhook(url, payload):
            captured["url"] = url
            captured["payload"] = payload

        with patch("app.core.agent_engine._fire_webhook", side_effect=fake_fire_webhook):
            await _fire_error_webhook(workflow, exc, None, "my prompt")

        assert captured["url"] == "https://example.com/error-hook"
        payload = captured["payload"]
        assert payload["status"] == "failed"
        assert payload["error_type"] == "internal_error"
        assert "boom" in payload["error_message"]
        assert payload["error_code"] is None
        assert payload["workflow_id"] == "wf-123"

    @pytest.mark.asyncio
    async def test_webhook_failure_does_not_propagate(self):
        """Even if the underlying HTTP call fails, _fire_error_webhook does not raise."""
        workflow = MagicMock()
        workflow.error_webhook_url = "https://bad-host.invalid/error-hook"
        workflow.id = "wf-999"
        workflow.title = "Broken Workflow"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network failure"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.core.agent_engine.httpx.AsyncClient", return_value=mock_client):
            # Should complete without raising
            await _fire_error_webhook(workflow, RuntimeError("original error"), None, "prompt")

