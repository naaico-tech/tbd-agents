"""Integration tests: SSE streaming endpoint for workflow events.

Verifies the `/api/workflows/{id}/stream` endpoint delivers events
published through the event bus as Server-Sent Events.

Closes #37
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.models.task_execution import TaskExecution, TaskStatus

from .conftest import create_agent, create_workflow


class TestSSEStreaming:
    @pytest.mark.asyncio
    async def test_stream_receives_published_events(self, app_client: httpx.AsyncClient):
        """Events published via event_bus appear in the SSE stream."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf_id = str(wf.id)

        events_to_deliver = [
            json.dumps({"type": "log", "data": {"event": "Starting agent"}}),
            json.dumps({"type": "message_delta", "data": {"delta": "Hello"}}),
            json.dumps({"type": "message_delta", "data": {"delta": " world"}}),
            json.dumps({"type": "status", "data": {"status": "completed"}}),
            None,  # signals end
        ]

        async def fake_subscribe(workflow_id, last_event_id=None):
            for evt in events_to_deliver:
                if evt is None:
                    return
                yield evt

        with patch("app.core.event_bus.subscribe", side_effect=fake_subscribe):
            resp = await app_client.get(
                f"/api/workflows/{wf_id}/stream",
                headers={"Accept": "text/event-stream"},
            )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        lines = resp.text.strip().split("\n\n")
        data_payloads = []
        for block in lines:
            for line in block.split("\n"):
                if line.startswith("data: "):
                    data_payloads.append(json.loads(line[6:]))

        assert any(p.get("type") == "log" for p in data_payloads)
        assert any(p.get("type") == "message_delta" for p in data_payloads)
        assert any(p.get("type") == "status" for p in data_payloads)

    @pytest.mark.asyncio
    async def test_stream_keepalive_on_none(self, app_client: httpx.AsyncClient):
        """None from subscribe yields a keepalive comment, not data."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf_id = str(wf.id)

        async def fake_subscribe(workflow_id, last_event_id=None):
            yield None  # keepalive
            yield json.dumps({"type": "status", "data": {"status": "completed"}})

        with patch("app.core.event_bus.subscribe", side_effect=fake_subscribe):
            resp = await app_client.get(f"/api/workflows/{wf_id}/stream")

        assert resp.status_code == 200
        # Keepalive lines start with ":"
        assert ": keepalive" in resp.text

    @pytest.mark.asyncio
    async def test_stream_resumes_with_last_event_id(self, app_client: httpx.AsyncClient):
        """Sending Last-Event-ID header passes resume_id to subscribe."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf_id = str(wf.id)

        captured_args: dict = {}

        async def fake_subscribe(workflow_id, last_event_id=None):
            captured_args["workflow_id"] = workflow_id
            captured_args["last_event_id"] = last_event_id
            # Replay one "missed" event then a live event
            yield json.dumps({"id": 5, "type": "log", "data": {"replayed": True}})
            yield json.dumps({"id": 6, "type": "status", "data": {"status": "completed"}})

        with patch("app.core.event_bus.subscribe", side_effect=fake_subscribe):
            resp = await app_client.get(
                f"/api/workflows/{wf_id}/stream",
                headers={"Last-Event-ID": "4"},
            )

        assert resp.status_code == 200
        assert captured_args["last_event_id"] == 4

        # Verify replayed event has an id: field in SSE output
        assert "id: 5" in resp.text
        assert "id: 6" in resp.text

    @pytest.mark.asyncio
    async def test_prompt_triggers_task_and_returns_running(
        self, app_client: httpx.AsyncClient, auth_headers: dict,
    ):
        """POST /prompt creates a TaskExecution and returns status=running."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf_id = str(wf.id)

        with patch("app.api.routes.workflows.run_agent_task.delay") as mock_delay:
            mock_delay.return_value = type("AsyncResult", (), {"id": "celery-abc"})()

            resp = await app_client.post(
                f"/api/workflows/{wf_id}/prompt",
                json={"prompt": "Hello integration test"},
                headers=auth_headers,
            )

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "running"

        # TaskExecution was persisted
        tasks = await TaskExecution.find(
            TaskExecution.workflow_id == wf_id,
        ).to_list()
        assert len(tasks) >= 1
        assert tasks[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_halt_sets_signal(
        self, app_client: httpx.AsyncClient, auth_headers: dict, mock_event_bus,
    ):
        """POST /halt sets the halt flag via event_bus."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf_id = str(wf.id)

        # Create a running task so halt endpoint doesn't 404
        task = TaskExecution(
            workflow_id=wf_id, prompt="running", status=TaskStatus.RUNNING,
        )
        await task.insert()

        resp = await app_client.post(
            f"/api/workflows/{wf_id}/halt",
            headers=auth_headers,
        )

        assert resp.status_code == 202
        # The mock_event_bus should have received a set_halt call
        assert mock_event_bus.set_halt.called
