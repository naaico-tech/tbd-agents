"""FastAPI dependency-injection factories for all model repositories.

Usage example in a route::

    from fastapi import Depends
    from app.repositories.deps import get_agent_repo
    from app.repositories.base import Repository
    from app.models.agent import Agent

    @router.get("/agents")
    async def list_agents(repo: Repository[Agent] = Depends(get_agent_repo)):
        return await repo.find_all()

The factory functions inspect ``DB_BACKEND`` at *request time* (via
``get_db_backend()``) so the backend can be switched without restarting.
"""
from __future__ import annotations

from app.db import get_db_backend
from app.repositories.base import Repository
from app.repositories.beanie_repo import BeanieRepository
from app.repositories.postgres_repo import PostgresRepository

# ---------------------------------------------------------------------------
# Lazy model imports — avoid circular imports and heavy top-level side effects.
# Each factory imports its model locally so this module can be imported even
# before the application has finished initialising all models.
# ---------------------------------------------------------------------------


def get_agent_repo() -> Repository:
    """Return the active repository for :class:`~app.models.agent.Agent`."""
    from app.models.agent import Agent  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Agent)
    return BeanieRepository(Agent)


def get_chat_session_repo() -> Repository:
    """Return the active repository for :class:`~app.models.chat_session.ChatSession`."""
    from app.models.chat_session import ChatSession  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(ChatSession)
    return BeanieRepository(ChatSession)


def get_chat_message_repo() -> Repository:
    """Return the active repository for :class:`~app.models.chat_message.ChatMessage`."""
    from app.models.chat_message import ChatMessage  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(ChatMessage)
    return BeanieRepository(ChatMessage)


def get_memory_repo() -> Repository:
    """Return the active repository for :class:`~app.models.memory.Memory`."""
    from app.models.memory import Memory  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Memory)
    return BeanieRepository(Memory)


def get_skill_repo() -> Repository:
    """Return the active repository for :class:`~app.models.skill.Skill`."""
    from app.models.skill import Skill  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Skill)
    return BeanieRepository(Skill)


def get_token_repo() -> Repository:
    """Return the active repository for :class:`~app.models.token.Token`."""
    from app.models.token import Token  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Token)
    return BeanieRepository(Token)


def get_provider_repo() -> Repository:
    """Return the active repository for :class:`~app.models.provider.Provider`."""
    from app.models.provider import Provider  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Provider)
    return BeanieRepository(Provider)


def get_knowledge_item_repo() -> Repository:
    """Return the active repository for :class:`~app.models.knowledge_item.KnowledgeItem`."""
    from app.models.knowledge_item import KnowledgeItem  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(KnowledgeItem)
    return BeanieRepository(KnowledgeItem)


def get_knowledge_source_repo() -> Repository:
    """Return the active repository for :class:`~app.models.knowledge_source.KnowledgeSource`."""
    from app.models.knowledge_source import KnowledgeSource  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(KnowledgeSource)
    return BeanieRepository(KnowledgeSource)


def get_custom_tool_repo() -> Repository:
    """Return the active repository for :class:`~app.models.custom_tool.CustomTool`."""
    from app.models.custom_tool import CustomTool  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(CustomTool)
    return BeanieRepository(CustomTool)


def get_guardrail_repo() -> Repository:
    """Return the active repository for :class:`~app.models.guardrail.Guardrail`."""
    from app.models.guardrail import Guardrail  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Guardrail)
    return BeanieRepository(Guardrail)


def get_workflow_repo() -> Repository:
    """Return the active repository for :class:`~app.models.workflow.Workflow`."""
    from app.models.workflow import Workflow  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(Workflow)
    return BeanieRepository(Workflow)


def get_task_execution_repo() -> Repository:
    """Return the active repository for :class:`~app.models.task_execution.TaskExecution`."""
    from app.models.task_execution import TaskExecution  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(TaskExecution)
    return BeanieRepository(TaskExecution)


def get_scheduled_agent_repo() -> Repository:
    """Return the active repository for :class:`~app.models.scheduled_agent.ScheduledAgent`."""
    from app.models.scheduled_agent import ScheduledAgent  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(ScheduledAgent)
    return BeanieRepository(ScheduledAgent)


def get_mcp_server_repo() -> Repository:
    """Return the active repository for :class:`~app.models.mcp_server.McpServer`."""
    from app.models.mcp_server import McpServer  # noqa: PLC0415

    if get_db_backend() == "postgres":
        return PostgresRepository(McpServer)
    return BeanieRepository(McpServer)
