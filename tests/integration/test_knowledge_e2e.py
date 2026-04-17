"""Integration tests: knowledge injection into agent system prompts.

Verifies that KnowledgeSource + KnowledgeItem documents stored in MongoDB
are aggregated by KnowledgeManager and injected into the system prompt
sent to the model.

Closes #40
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import run_agent
from app.models.knowledge_item import KnowledgeContentType, KnowledgeItem
from app.models.knowledge_source import (
    KnowledgeSource,
    KnowledgeSourceStatus,
    KnowledgeSourceType,
)
from app.models.task_execution import TaskExecution, TaskStatus

from .conftest import create_agent, create_workflow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_text_source(
    name: str, items: list[dict], *, source_tags: list[str] | None = None,
) -> KnowledgeSource:
    """Create a KnowledgeSource with embedded text items."""
    source = KnowledgeSource(
        name=name,
        source_type=KnowledgeSourceType.MONGO_DB,
        status=KnowledgeSourceStatus.CONNECTED,
        tags=source_tags or [],
    )
    await source.insert()

    for item in items:
        ki = KnowledgeItem(
            source_id=str(source.id),
            text_content=item["content"],
            content_type=KnowledgeContentType.TEXT,
            name=item.get("name", "item"),
            tags=item.get("tags", []),
        )
        await ki.insert()

    return source


def _make_fake_session(captured_prompts: list):
    """Build a mock SDK client + session that captures system_message and fires events."""
    _on_callback = None

    class _FakeSession:
        session_id = "test-session-knowledge"

        class _client:
            @staticmethod
            async def request(*args, **kwargs):
                if _on_callback is None:
                    return
                _on_callback(SimpleNamespace(
                    type=SimpleNamespace(value="assistant.message"),
                    data=SimpleNamespace(content="OK"),
                ))
                _on_callback(SimpleNamespace(
                    type=SimpleNamespace(value="session.idle"),
                    data=None,
                ))

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def on(self, callback):
            nonlocal _on_callback
            _on_callback = callback

    def capture_create_session(**kwargs):
        sm = kwargs.get("system_message", {})
        captured_prompts.append(sm.get("content", "") if isinstance(sm, dict) else "")
        return _FakeSession()

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.create_session = AsyncMock(side_effect=capture_create_session)
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKnowledgeInjection:
    @pytest.mark.asyncio
    async def test_knowledge_context_in_system_prompt(self, mock_event_bus):
        """Knowledge items are aggregated and appear in the system prompt."""
        source = await _create_text_source("company-policy", [
            {"content": "All responses must be professional.", "name": "tone", "tags": ["policy"]},
            {"content": "Never share internal pricing.", "name": "pricing", "tags": ["policy"]},
        ], source_tags=["policy"])
        agent = await create_agent(
            knowledge_source_ids=[str(source.id)], knowledge_tags=["policy"],
        )
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="What are the rules?", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_prompts: list[str] = []

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_build.return_value = _make_fake_session(captured_prompts)

            await run_agent(
                wf, "What are the rules?", "ghp_token",
                task_execution_id=str(task.id),
            )

        # Knowledge should appear in the system prompt
        assert len(captured_prompts) > 0
        sys_prompt = captured_prompts[0]
        assert "professional" in sys_prompt.lower() or "<knowledge>" in sys_prompt

    @pytest.mark.asyncio
    async def test_tag_based_knowledge_loading(self, mock_event_bus):
        """Knowledge items matched by tags are included."""
        source = await _create_text_source("faq", [
            {"content": "Return policy: 30 days.", "name": "returns", "tags": ["support"]},
            {"content": "Warranty: 1 year.", "name": "warranty", "tags": ["support"]},
        ])
        agent = await create_agent(
            knowledge_source_ids=[], knowledge_tags=["support"],
        )
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Support question", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_prompts: list[str] = []

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_build.return_value = _make_fake_session(captured_prompts)

            await run_agent(
                wf, "Support question", "ghp_token",
                task_execution_id=str(task.id),
            )

        assert len(captured_prompts) > 0
        sys_prompt = captured_prompts[0]
        # At least one knowledge item should be present
        assert "30 days" in sys_prompt or "1 year" in sys_prompt or "<knowledge>" in sys_prompt

    @pytest.mark.asyncio
    async def test_no_knowledge_sources_empty_context(self, mock_event_bus):
        """Agent with no knowledge sources gets an empty knowledge context."""
        agent = await create_agent(knowledge_source_ids=[], knowledge_tags=[])
        wf = await create_workflow(agent)
        task = TaskExecution(
            workflow_id=str(wf.id), prompt="Simple question", status=TaskStatus.PENDING,
        )
        await task.insert()

        captured_prompts: list[str] = []

        with (
            patch("app.core.agent_engine.memory_manager") as mock_mm,
            patch("app.core.agent_engine._sync_repo", new_callable=AsyncMock, return_value=None),
            patch("app.core.agent_engine.build_client") as mock_build,
        ):
            mock_mm.build_memory_context = AsyncMock(return_value="")
            mock_build.return_value = _make_fake_session(captured_prompts)

            await run_agent(
                wf, "Simple question", "ghp_token",
                task_execution_id=str(task.id),
            )

        assert len(captured_prompts) > 0
        # No <knowledge> block should be present
        assert "<knowledge>" not in captured_prompts[0]
