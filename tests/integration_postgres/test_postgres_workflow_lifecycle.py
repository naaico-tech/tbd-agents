"""PostgreSQL integration tests: Workflow status lifecycle.

Verifies that the workflow state machine transitions work correctly end-to-end
against a real PostgreSQL database, including:

  - ACTIVE → RUNNING (when a task starts)
  - RUNNING → ACTIVE (when a task completes or fails)
  - Concurrency guard: a second prompt is rejected while RUNNING
  - Terminal states (FAILED, COMPLETED, HALTED) auto-reset to ACTIVE
    when the prompt endpoint receives a new request

Run with:
    DB_BACKEND=postgres \\
      TEST_POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5433/tbd_agents_integration_test \\
      pytest tests/integration/postgres/test_postgres_workflow_lifecycle.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from .conftest import create_agent, create_task, create_workflow


class TestWorkflowStatusPersistence:
    """Workflow status enum transitions persist to PostgreSQL correctly."""

    @pytest.mark.asyncio
    async def test_default_status_is_active(self):
        """A freshly inserted workflow starts in ACTIVE status."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)

        fetched = await Workflow.get(wf.id)
        assert fetched.status == WorkflowStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_status_set_to_running(self):
        """Setting status to RUNNING and saving persists correctly."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus.RUNNING
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert fetched.status == WorkflowStatus.RUNNING

    @pytest.mark.asyncio
    async def test_status_reset_to_active(self):
        """Resetting from RUNNING back to ACTIVE persists correctly."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus.RUNNING
        await wf.save()

        wf.status = WorkflowStatus.ACTIVE
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert fetched.status == WorkflowStatus.ACTIVE

    @pytest.mark.asyncio
    @pytest.mark.parametrize("terminal_status", [
        "failed", "completed", "halted", "max_turns_reached",
    ])
    async def test_all_terminal_statuses_persist(self, terminal_status: str):
        """Each terminal status value persists and round-trips correctly."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus(terminal_status)
        await wf.save()

        fetched = await Workflow.get(wf.id)
        assert fetched.status == WorkflowStatus(terminal_status)

    @pytest.mark.asyncio
    async def test_concurrent_saves_preserve_last_write(self):
        """Two sequential saves do not lose data (last-write-wins semantics)."""
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)

        # Simulate two separate fetch + modify + save cycles
        wf_copy_a = await Workflow.get(wf.id)
        wf_copy_b = await Workflow.get(wf.id)

        wf_copy_a.status = WorkflowStatus.RUNNING
        await wf_copy_a.save()

        wf_copy_b.status = WorkflowStatus.ACTIVE
        await wf_copy_b.save()

        final = await Workflow.get(wf.id)
        # Last save wins
        assert final.status == WorkflowStatus.ACTIVE


class TestWorkflowConcurrencyGuard:
    """Verify the RUNNING guard prevents concurrent task submission."""

    @pytest.mark.asyncio
    async def test_running_workflow_blocks_new_prompt_via_api(self):
        """The /api/workflows/{id}/prompt endpoint returns 400 when RUNNING."""
        import httpx

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = "running"
        await wf.save()

        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.main.init_telemetry"),
            patch("app.main.Instrumentator") as mock_instr,
        ):
            mock_instr.return_value.instrument.return_value.expose = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
            from app.main import app

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workflows/{wf.id}/prompt",
                    headers={"Authorization": "Bearer ghp_test"},
                    json={"prompt": "Are you busy?"},
                )

        assert resp.status_code == 400
        assert "running" in resp.text.lower() or "busy" in resp.text.lower() or "in progress" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_active_workflow_accepts_prompt(self):
        """The prompt endpoint accepts a new prompt when workflow is ACTIVE."""
        import httpx
        from app.models.workflow import WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        assert wf.status == WorkflowStatus.ACTIVE  # default

        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.main.init_telemetry"),
            patch("app.main.Instrumentator") as mock_instr,
            patch("app.api.routes.workflows.run_agent_task") as mock_task,
        ):
            mock_instr.return_value.instrument.return_value.expose = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
            mock_task.delay = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(return_value=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(id="celery-task-id"))
            from app.main import app

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workflows/{wf.id}/prompt",
                    headers={"Authorization": "Bearer ghp_test"},
                    json={"prompt": "Hello!"},
                )

        # Should be 200 (task dispatched) or 202 — NOT 400
        assert resp.status_code in (200, 201, 202)

    @pytest.mark.asyncio
    async def test_terminal_workflow_auto_resets_on_prompt(self):
        """Terminal states auto-reset to ACTIVE when a new prompt is submitted."""
        import httpx
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus.FAILED
        await wf.save()

        with (
            patch("app.main.init_db", new_callable=AsyncMock),
            patch("app.main.init_telemetry"),
            patch("app.main.Instrumentator") as mock_instr,
            patch("app.api.routes.workflows.run_agent_task") as mock_task,
        ):
            mock_instr.return_value.instrument.return_value.expose = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
            mock_task.delay = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(return_value=__import__("unittest.mock", fromlist=["MagicMock"]).MagicMock(id="celery-task-id"))
            from app.main import app

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    f"/api/workflows/{wf.id}/prompt",
                    headers={"Authorization": "Bearer ghp_test"},
                    json={"prompt": "Try again!"},
                )

        assert resp.status_code in (200, 201, 202)

        # Workflow should have been reset to ACTIVE
        fetched = await Workflow.get(wf.id)
        # The endpoint resets status before dispatching the Celery task
        assert fetched.status in (WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING)


class TestWorkflowCurrentTurn:
    """current_turn increments correctly across saves."""

    @pytest.mark.asyncio
    async def test_current_turn_increments(self):
        """current_turn integer field increments and persists correctly."""
        from app.models.workflow import Workflow

        agent = await create_agent()
        wf = await create_workflow(agent)
        assert wf.current_turn == 0

        for turn in range(1, 6):
            wf.current_turn = turn
            await wf.save()
            fetched = await Workflow.get(wf.id)
            assert fetched.current_turn == turn


class TestWorkflowTaskRelationship:
    """Workflow ↔ TaskExecution relationship queries."""

    @pytest.mark.asyncio
    async def test_tasks_linked_to_workflow(self):
        """TaskExecution.find() by workflow_id returns all linked tasks."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)

        task1 = await create_task(wf, prompt="First task")
        task2 = await create_task(wf, prompt="Second task")
        task2.status = TaskStatus.COMPLETED
        await task2.save()

        all_tasks = await TaskExecution.find({"workflow_id": str(wf.id)}).to_list()
        assert len(all_tasks) == 2
        statuses = {t.status for t in all_tasks}
        assert TaskStatus.PENDING in statuses
        assert TaskStatus.COMPLETED in statuses

    @pytest.mark.asyncio
    async def test_running_task_detected(self):
        """A running task can be found for a workflow by status."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)

        task = await create_task(wf, prompt="active work")
        task.status = TaskStatus.RUNNING
        await task.save()

        running = await TaskExecution.find_one({
            "workflow_id": str(wf.id),
            "status": TaskStatus.RUNNING,
        })
        assert running is not None
        assert running.id == task.id

    @pytest.mark.asyncio
    async def test_no_running_task_returns_none(self):
        """find_one for RUNNING returns None when no task is running."""
        from app.models.task_execution import TaskExecution, TaskStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        await create_task(wf, status=TaskStatus.COMPLETED)

        running = await TaskExecution.find_one({
            "workflow_id": str(wf.id),
            "status": TaskStatus.RUNNING,
        })
        assert running is None

    @pytest.mark.asyncio
    async def test_task_count_per_workflow(self):
        """PgQuerySet.count() filtered by workflow_id returns correct count."""
        from app.models.task_execution import TaskExecution

        agent = await create_agent()
        wf_a = await create_workflow(agent)
        wf_b = await create_workflow(agent)

        await create_task(wf_a)
        await create_task(wf_a)
        await create_task(wf_a)
        await create_task(wf_b)

        count_a = await TaskExecution.find({"workflow_id": str(wf_a.id)}).count()
        count_b = await TaskExecution.find({"workflow_id": str(wf_b.id)}).count()
        assert count_a == 3
        assert count_b == 1
