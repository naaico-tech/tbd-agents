from typing import Any

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.models.agent import Agent
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.custom_tool import CustomTool
from app.models.guardrail import Guardrail
from app.models.knowledge_item import KnowledgeItem
from app.models.knowledge_source import KnowledgeSource
from app.models.mcp_server import McpServer
from app.models.memory import Memory
from app.models.provider import Provider
from app.models.scheduled_agent import ScheduledAgent
from app.models.skill import Skill
from app.models.task_execution import TaskExecution
from app.models.token import Token
from app.models.workflow import Workflow


def get_db_backend() -> str:
    """Return the configured database backend (``'mongo'`` or ``'postgres'``)."""
    return settings.db_backend


async def init_db() -> None:
    """Initialise the configured database backend.

    * ``db_backend = "postgres"`` → create all structured (typed) tables via SQLAlchemy.
    * ``db_backend = "mongo"`` (default) → run Beanie / Motor initialisation.
    """
    if settings.db_backend == "postgres":
        from app.db_postgres import init_postgres  # noqa: PLC0415

        await init_postgres()
        return

    # Default: MongoDB + Beanie
    client = AsyncIOMotorClient(settings.mongo_uri)
    await init_beanie(
        database=client[settings.mongo_db_name],
        document_models=[
            Agent,
            ChatMessage,
            ChatSession,
            CustomTool,
            Guardrail,
            KnowledgeItem,
            KnowledgeSource,
            McpServer,
            Memory,
            Provider,
            ScheduledAgent,
            Skill,
            TaskExecution,
            Token,
            Workflow,
        ],
    )


async def close_db() -> None:
    """Gracefully close the active database backend connection."""
    if settings.db_backend == "postgres":
        from app.db_postgres import close_postgres  # noqa: PLC0415

        await close_postgres()


def parse_doc_id(id_str: str) -> Any:
    """Return a document ID in the type expected by the active backend.

    * PostgreSQL backend → plain string (UUID format).
    * MongoDB backend → ``PydanticObjectId`` for Beanie compatibility.
    """
    if settings.db_backend == "postgres":
        return id_str
    from beanie import PydanticObjectId  # noqa: PLC0415
    return PydanticObjectId(id_str)
