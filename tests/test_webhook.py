"""Tests for webhook dispatch after task completion."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import _fire_webhook


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
