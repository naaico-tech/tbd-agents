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


async def init_db() -> None:
    client = AsyncIOMotorClient(settings.mongo_uri)
    await init_beanie(
        database=client[settings.mongo_db_name],
        document_models=[
            Agent, ChatMessage, ChatSession, CustomTool, Guardrail, KnowledgeItem,
            KnowledgeSource, McpServer, Memory, Provider, ScheduledAgent, Skill,
            TaskExecution, Token, Workflow,
        ],
    )
