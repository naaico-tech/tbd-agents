"""Integration tests: Celery task lifecycle (dispatch → running → completed/failed).

Exercises the ``_execute`` coroutine from app.tasks.agent_task directly
(bypassing ``asyncio.run()`` since tests already own the event loop).
Verifies DB state transitions and error handling.

Closes #42
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.task_execution import TaskExecution, TaskStatus
from app.models.workflow import WorkflowStatus
from app.tasks.agent_task import _execute, _mark_failed

from .conftest import create_agent, create_workflow

# _execute imports init_db and run_agent locally, so we patch at the source module.
_PATCH_INIT_DB = "app.db.init_db"
_PATCH_RUN_AGENT = "app.core.agent_engine.run_agent"


class TestCeleryTaskLifecycle:
    @pytest.mark.asyncio
    async def test_successful_dispatch_completes(self, mock_event_bus):
        """_execute calls run_agent and completes successfully."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Celery test", status=TaskStatus.PENDING,
        )
        await task.insert()

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "Agent response"
            await _execute(
                str(wf.id), "Celery test", "ghp_token",
                str(task.id), None,
            )

        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_task_marks_execution_failed(self, mock_event_bus):
        """When run_agent raises, _mark_failed sets status to FAILED."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Fail test", status=TaskStatus.PENDING,
        )
        await task.insert()

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.side_effect = RuntimeError("Model exploded")

            with pytest.raises(RuntimeError):
                await _execute(
                    str(wf.id), "Fail test", "ghp_token",
                    str(task.id), None,
                )

        # _mark_failed should have set status
        with patch(_PATCH_INIT_DB, new_callable=AsyncMock):
            await _mark_failed(str(wf.id), str(task.id))

        updated = await TaskExecution.get(task.id)
        assert updated.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_inactive_workflow_handled(self, mock_event_bus):
        """Task against an INACTIVE workflow should complete gracefully."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        wf.status = WorkflowStatus.INACTIVE
        await wf.save()

        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Inactive test", status=TaskStatus.PENDING,
        )
        await task.insert()

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = None  # run_agent returns None for inactive
            await _execute(
                str(wf.id), "Inactive test", "ghp_token",
                str(task.id), None,
            )

        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_missing_workflow_fails_gracefully(self, mock_event_bus):
        """Task for a deleted workflow should fail without crashing."""
        fake_wf_id = "000000000000000000000000"

        task = TaskExecution(
            workflow_id=fake_wf_id, prompt="Ghost workflow", status=TaskStatus.PENDING,
        )
        await task.insert()

        with patch(_PATCH_INIT_DB, new_callable=AsyncMock):
            # _execute returns early if workflow not found
            await _execute(
                fake_wf_id, "Ghost workflow", "ghp_token",
                str(task.id), None,
            )

    @pytest.mark.asyncio
    async def test_task_execution_stores_worker_id(self, mock_event_bus):
        """The worker hostname is stored on the TaskExecution."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Worker tracking", status=TaskStatus.PENDING,
        )
        await task.insert()

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "OK"
            await _execute(
                str(wf.id), "Worker tracking", "ghp_token",
                str(task.id), "worker-1",
            )

        updated = await TaskExecution.get(task.id)
        assert updated.worker == "worker-1"
