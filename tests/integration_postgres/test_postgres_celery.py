"""PostgreSQL integration tests: Celery task lifecycle.

Mirrors ``tests/integration/test_celery_tasks.py`` but exercises the
``_execute`` / ``_mark_failed`` coroutines against a *real* PostgreSQL
database rather than MongoDB.

Verifies:
  - Successful dispatch: run_agent called, TaskExecution set to COMPLETED
  - Failed dispatch: _mark_failed resets workflow to ACTIVE, task to FAILED
  - Workflow transitions to RUNNING while task is in progress
  - Worker hostname is stored on the TaskExecution record

Run with:
    DB_BACKEND=postgres \\
      TEST_POSTGRES_URI=postgresql+asyncpg://postgres:postgres@localhost:5433/tbd_agents_integration_test \\
      pytest tests/integration/postgres/test_postgres_celery.py -v
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from .conftest import create_agent, create_task, create_workflow

_PATCH_INIT_DB = "app.db.init_db"
_PATCH_CLOSE_DB = "app.db.close_db"
_PATCH_RUN_AGENT = "app.core.agent_engine.run_agent"


class TestPostgresCeleryTaskLifecycle:
    """Celery _execute / _mark_failed exercised with a real PostgreSQL DB."""

    @pytest.mark.asyncio
    async def test_successful_task_sets_worker(self):
        """A successful _execute stores the worker hostname on TaskExecution."""
        from app.models.task_execution import TaskExecution, TaskStatus
        from app.tasks.agent_task import _execute

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="Postgres celery test")

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "Agent responded"
            await _execute(
                str(wf.id), "Postgres celery test", "ghp_token",
                str(task.id), "celery@worker-pg-1",
            )

        updated = await TaskExecution.get(task.id)
        assert updated.worker == "celery@worker-pg-1"
        assert updated.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_successful_task_completes(self):
        """run_agent is called exactly once and TaskExecution status is COMPLETED."""
        from app.models.task_execution import TaskExecution, TaskStatus
        from app.tasks.agent_task import _execute

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="Success path")

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "Done"
            await _execute(str(wf.id), "Success path", "ghp_token", str(task.id), None)

        mock_run.assert_called_once()
        final_task = await TaskExecution.get(task.id)
        assert final_task.status == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_failed_task_marks_execution_failed(self):
        """When run_agent raises, _mark_failed sets TaskExecution.status=FAILED."""
        from app.models.task_execution import TaskExecution, TaskStatus
        from app.tasks.agent_task import _execute, _mark_failed

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="Failure path")

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.side_effect = RuntimeError("Model exploded")
            with pytest.raises(RuntimeError):
                await _execute(str(wf.id), "Failure path", "ghp_token", str(task.id), None)

        # Now call _mark_failed directly (as agent_task.py does in the except block)
        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
        ):
            await _mark_failed(str(wf.id), str(task.id))

        final_task = await TaskExecution.get(task.id)
        assert final_task.status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_mark_failed_resets_workflow_to_active(self):
        """_mark_failed resets workflow.status from RUNNING back to ACTIVE."""
        from app.models.workflow import Workflow, WorkflowStatus
        from app.tasks.agent_task import _mark_failed

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf)

        # Simulate task starting — set workflow to RUNNING
        wf.status = WorkflowStatus.RUNNING
        await wf.save()

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
        ):
            await _mark_failed(str(wf.id), str(task.id))

        final_wf = await Workflow.get(wf.id)
        assert final_wf.status == WorkflowStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_missing_workflow_fails_gracefully(self):
        """_execute against a missing workflow returns without raising."""
        from app.tasks.agent_task import _execute
        import uuid

        fake_wf_id = str(uuid.uuid4())
        fake_task_id = str(uuid.uuid4())

        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
        ):
            # Should not raise — missing workflow is handled gracefully
            await _execute(fake_wf_id, "Ghost prompt", "ghp_token", fake_task_id, None)

    @pytest.mark.asyncio
    async def test_multiple_sequential_tasks_on_same_workflow(self):
        """Multiple sequential tasks all complete and are recorded correctly."""
        from app.models.task_execution import TaskExecution, TaskStatus
        from app.tasks.agent_task import _execute

        agent = await create_agent()
        wf = await create_workflow(agent)

        for i in range(3):
            task = await create_task(wf, prompt=f"Sequential task {i}")
            with (
                patch(_PATCH_INIT_DB, new_callable=AsyncMock),
                patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
                patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
            ):
                mock_run.return_value = f"Response {i}"
                await _execute(str(wf.id), f"Sequential task {i}", "ghp_token", str(task.id), None)

        all_tasks = await TaskExecution.find({"workflow_id": str(wf.id)}).to_list()
        assert len(all_tasks) == 3
        assert all(t.status == TaskStatus.COMPLETED for t in all_tasks)

    @pytest.mark.asyncio
    async def test_task_finished_at_set_on_completion(self):
        """finished_at timestamp is set when a task completes."""
        from datetime import UTC, datetime
        from app.models.task_execution import TaskExecution
        from app.tasks.agent_task import _execute

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="Timestamp check")

        before = datetime.now(UTC)
        with (
            patch(_PATCH_INIT_DB, new_callable=AsyncMock),
            patch(_PATCH_CLOSE_DB, new_callable=AsyncMock),
            patch(_PATCH_RUN_AGENT, new_callable=AsyncMock) as mock_run,
        ):
            mock_run.return_value = "Done"
            await _execute(str(wf.id), "Timestamp check", "ghp_token", str(task.id), None)
        after = datetime.now(UTC)

        final = await TaskExecution.get(task.id)
        assert final.finished_at is not None
        assert before <= final.finished_at <= after


class TestPostgresWorkflowRunningState:
    """Verify RUNNING state is set and cleared correctly by the agent engine."""

    @pytest.mark.asyncio
    async def test_run_agent_sets_running_then_active(self, mock_event_bus):
        """run_agent sets workflow.status=RUNNING at start and ACTIVE at end."""
        from types import SimpleNamespace
        from unittest.mock import MagicMock
        from app.core.agent_engine import run_agent
        from app.models.task_execution import TaskExecution, TaskStatus
        from app.models.workflow import Workflow, WorkflowStatus

        agent = await create_agent()
        wf = await create_workflow(agent)
        task = await create_task(wf, prompt="Running state test")

        status_snapshots: list[str] = []

        # Capture workflow status mid-execution by intercepting save()
        original_save = Workflow.save

        async def capturing_save(self):
            status_snapshots.append(str(self.status))
            return await original_save(self)

        _on_callback = None

        class _FakeSession:
            session_id = "fake-pg-session-123"

            class _Client:
                @staticmethod
                async def request(*args, **kwargs):
                    if _on_callback is None:
                        return
                    _on_callback(SimpleNamespace(
                        type=SimpleNamespace(value="assistant.message"),
                        data=SimpleNamespace(content="Hello from PG test!"),
                    ))
                    _on_callback(SimpleNamespace(
                        type=SimpleNamespace(value="session.idle"),
                        data=None,
                    ))

            _client = _Client()

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            def on(self, callback):
                nonlocal _on_callback
                _on_callback = callback

        session = _FakeSession()

        with (
            patch("app.core.agent_engine.build_client") as mock_build,
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch.object(Workflow, "save", capturing_save),
        ):
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.create_session = AsyncMock(return_value=session)
            mock_build.return_value = mock_client
            mock_mm.build_memory_context = AsyncMock(return_value="")

            result = await run_agent(wf, "Running state test", "ghp_token", task_execution_id=str(task.id))

        assert result is not None
        # RUNNING should appear in status snapshots (set at task start)
        assert WorkflowStatus.RUNNING in status_snapshots or "running" in status_snapshots

        # Final DB state should be ACTIVE (auto-reset on completion)
        final_wf = await Workflow.get(wf.id)
        assert final_wf.status == WorkflowStatus.ACTIVE

        # Task should be COMPLETED
        final_task = await TaskExecution.get(task.id)
        assert final_task.status == TaskStatus.COMPLETED
