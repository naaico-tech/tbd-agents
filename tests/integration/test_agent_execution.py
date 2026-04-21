"""Integration tests: full agent execution loop via the Copilot SDK path.

Mocks the Copilot SDK session layer so the test exercises:
  agent resolution → provider routing → system prompt construction →
  SDK session creation → event publishing → usage tracking → DB persistence.

Closes #35
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import run_agent
from app.models.task_execution import TaskExecution, TaskStatus
from app.models.workflow import WorkflowStatus

from .conftest import create_agent, create_skill, create_workflow

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_copilot_session(response_text: str = "Hello from Copilot!"):
    """Return a mock SDK session matching the real SDK interface.

    The real code flow is:
      async with await client.create_session(**kwargs) as session:
          session.on(callback)                     # register event handler
          await session._client.request(...)       # send message
          await asyncio.wait_for(done.wait(), ...) # wait for events

    The on_event callback is synchronous; it receives events with .type
    (has .value attr) and .data attributes, and calls asyncio.create_task().
    """
    _on_callback = None

    class _FakeSession:
        session_id = "fake-session-123"

        class _Client:
            @staticmethod
            async def request(*args, **kwargs):
                if _on_callback is None:
                    return
                # Emit assistant.message
                _on_callback(SimpleNamespace(
                    type=SimpleNamespace(value="assistant.message"),
                    data=SimpleNamespace(content=response_text),
                ))
                # Emit session.idle to signal completion
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

    return _FakeSession()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCopilotSDKExecution:
    @pytest.mark.asyncio
    async def test_successful_execution_saves_response(self, mock_event_bus):
        """Full loop: agent → workflow → run_agent (SDK path) → DB updated."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Say hello", status=TaskStatus.PENDING,
        )
        await task.insert()

        session = _mock_copilot_session("Hello from Copilot!")

        with (
            patch("app.core.agent_engine.build_client") as mock_build,
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
        ):
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.create_session = AsyncMock(return_value=session)
            mock_build.return_value = mock_client
            mock_mm.build_memory_context = AsyncMock(return_value="")

            result = await run_agent(
                wf, "Say hello", "ghp_fake_token",
                task_execution_id=str(task.id),
            )

        # Verify response persisted
        assert result is not None
        assert "Hello" in result

        # Task status updated
        updated_task = await TaskExecution.get(task.id)
        assert updated_task.status == TaskStatus.COMPLETED
        assert updated_task.response is not None
        assert updated_task.finished_at is not None

        # Events were published
        event_types = [e[1] for e in mock_event_bus.events]
        assert "log" in event_types
        assert "status" in event_types

    @pytest.mark.asyncio
    async def test_inactive_workflow_returns_none(self, mock_event_bus):
        """An INACTIVE workflow should abort immediately."""
        agent = await create_agent()
        wf = await create_workflow(agent, status=WorkflowStatus.INACTIVE)

        result = await run_agent(wf, "test", "ghp_token")
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_agent_fails(self, mock_event_bus):
        """If the agent record is deleted, run_agent should fail gracefully."""
        agent = await create_agent()
        wf = await create_workflow(agent)
        # Delete the agent
        await agent.delete()

        result = await run_agent(wf, "test", "ghp_token")
        assert result is None

        # A failure status event should be published
        status_events = [e for e in mock_event_bus.events if e[1] == "status"]
        assert any("failed" in str(e[2]) for e in status_events)

    @pytest.mark.asyncio
    async def test_skills_injected_into_system_prompt(self, mock_event_bus):
        """Skills should be appended to the system prompt."""
        skill = await create_skill(
            name="test-politeness",
            instructions="Always say please and thank you.",
        )
        agent = await create_agent(skill_ids=[str(skill.id)])
        wf = await create_workflow(agent, skill_ids=[str(skill.id)])
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Hello", status=TaskStatus.PENDING,
        )
        await task.insert()

        session = _mock_copilot_session("Hello!")
        captured_instructions = {}

        with (
            patch("app.core.agent_engine.build_client") as mock_build,
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
        ):
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            def capture_session(**kwargs):
                sm = kwargs.get("system_message", {})
                captured_instructions["system_prompt"] = (
                    sm.get("content", "") if isinstance(sm, dict) else ""
                )
                return session

            mock_client.create_session = AsyncMock(side_effect=capture_session)
            mock_build.return_value = mock_client
            mock_mm.build_memory_context = AsyncMock(return_value="")

            await run_agent(
                wf, "Hello", "ghp_token", task_execution_id=str(task.id),
            )

        # Verify the skill text was injected
        assert "please and thank you" in captured_instructions.get("system_prompt", "")

    @pytest.mark.asyncio
    async def test_caveman_workflow_compresses_injected_context(self, mock_event_bus):
        """Caveman workflows should add caveman policy and compress memory context."""
        agent = await create_agent()
        wf = await create_workflow(agent, caveman=True)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Hello", status=TaskStatus.PENDING,
        )
        await task.insert()

        session = _mock_copilot_session("Hello!")
        captured_instructions = {}
        memory_context = (
            "<memories>\n"
            "<memory key=\"prefs\" scope=\"agent\">"
            "It is important to make sure you always run `pytest` before push to main."
            "</memory>\n"
            "</memories>"
        )

        with (
            patch("app.core.agent_engine.build_client") as mock_build,
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
        ):
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)

            def capture_session(**kwargs):
                sm = kwargs.get("system_message", {})
                captured_instructions["system_prompt"] = (
                    sm.get("content", "") if isinstance(sm, dict) else ""
                )
                return session

            mock_client.create_session = AsyncMock(side_effect=capture_session)
            mock_build.return_value = mock_client
            mock_mm.build_memory_context = AsyncMock(return_value=memory_context)

            await run_agent(
                wf, "Hello", "ghp_token", task_execution_id=str(task.id),
            )

        prompt = captured_instructions.get("system_prompt", "")
        assert "<caveman_policy>" in prompt
        assert "run `pytest` before push main" in prompt
