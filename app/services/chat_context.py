"""Agent self-awareness context builder for chat system prompts.

Assembles a structured XML block describing the agent's identity, skills,
available tools (names only — no execution), and recent task history so the
agent can answer questions like "What can you do?" or "What have you been
working on?".
"""

import logging
from xml.sax.saxutils import escape

from beanie import PydanticObjectId

from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.skill import Skill
from app.models.task_execution import TaskExecution
from app.models.workflow import Workflow
from app.services.memory_manager import MemoryManager

logger = logging.getLogger(__name__)

# How many recent task executions to summarise
_TASK_HISTORY_LIMIT = 10

_memory_manager = MemoryManager()


async def build_chat_context(agent: Agent, github_user: str) -> str:
    """Build the self-awareness context block for a chat system prompt.

    Returns an XML string that is injected between the agent's base system
    prompt and the conversation history.  All sections are best-effort: a
    failure in any section is logged and silently skipped so that the chat
    still proceeds.

    Sections:
    - ``<agent_profile>`` — name, model, description
    - ``<skills>`` — installed skill names and descriptions
    - ``<available_tools>`` — tool names from MCP servers + builtins
    - ``<task_history>`` — recent task executions summarised
    - ``<memory>`` — STM/LTM memories via MemoryManager
    """
    parts: list[str] = ["<agent_context>"]

    # ── 1. Agent profile ─────────────────────────────────────────────────────
    try:
        parts.append(
            f"  <agent_profile>"
            f"<name>{escape(agent.name)}</name>"
            f"<model>{escape(agent.model or 'default')}</model>"
            f"<description>{escape(agent.description)}</description>"
            f"</agent_profile>"
        )
    except Exception as exc:
        logger.debug("chat_context: agent_profile failed: %s", exc)

    # ── 2. Skills ────────────────────────────────────────────────────────────
    try:
        skill_lines: list[str] = []
        skill_ids: list[str] = list(getattr(agent, "skill_ids", []) or [])

        # Skills are primarily attached to workflows in the current data model.
        # Fall back to collecting workflow skill IDs for this user/agent when
        # the agent record does not expose skill_ids directly.
        if not skill_ids:
            wf_skill_filter = {
                "github_user": github_user,
                "agent_id": str(getattr(agent, "id", None)),
            }
            wf_for_skills = await Workflow.find(wf_skill_filter).to_list()
            for wf in wf_for_skills:
                for sid in getattr(wf, "skill_ids", []) or []:
                    skill_ids.append(sid)

        for sid in dict.fromkeys(skill_ids):
            try:
                skill = await Skill.get(PydanticObjectId(sid))
            except Exception:
                continue
            if skill:
                skill_lines.append(
                    f"    <skill><name>{escape(skill.name)}</name>"
                    f"<description>{escape(skill.description)}</description></skill>"
                )
        if skill_lines:
            parts.append("  <skills>\n" + "\n".join(skill_lines) + "\n  </skills>")
    except Exception as exc:
        logger.debug("chat_context: skills failed: %s", exc)

    # ── 3. Available tools (names only) ─────────────────────────────────────
    try:
        tool_names: list[str] = []

        # Builtin tools declared on the agent
        tool_names.extend(agent.builtin_tools or [])

        # Custom tool definitions (just the function names)
        for td in agent.tool_definitions or []:
            fn = td.get("function", td)
            name = fn.get("name")
            if name and name not in tool_names:
                tool_names.append(name)

        # MCP server tools — collect from MCP server records (names only,
        # no live connections needed)
        mcp_server_ids = list(agent.mcp_server_ids or [])
        if agent.mcp_server_tags:
            tag_servers = await McpServer.find(
                {"tags": {"$in": agent.mcp_server_tags}}
            ).to_list()
            mcp_server_ids += [str(s.id) for s in tag_servers]
        mcp_server_ids = list(dict.fromkeys(mcp_server_ids))  # deduplicate

        for sid in mcp_server_ids:
            try:
                server = await McpServer.get(sid)
            except Exception:
                continue
            if server:
                # Use stored tool_names if available (cached from a previous run)
                stored = getattr(server, "tool_names", None) or []
                for tn in stored:
                    if tn not in tool_names:
                        tool_names.append(tn)

        if tool_names:
            tool_xml = "\n".join(
                f"    <tool>{escape(t)}</tool>" for t in tool_names
            )
            parts.append(f"  <available_tools>\n{tool_xml}\n  </available_tools>")
    except Exception as exc:
        logger.debug("chat_context: available_tools failed: %s", exc)

    # ── 4. Recent task history ───────────────────────────────────────────────
    try:
        # Find workflows belonging to this agent + user
        workflows = await Workflow.find(
            Workflow.agent_id == str(agent.id),
            Workflow.github_user == github_user,
        ).to_list()
        wf_ids = {str(wf.id) for wf in workflows}

        if wf_ids:
            recent_tasks = (
                await TaskExecution.find({"workflow_id": {"$in": list(wf_ids)}})
                .sort("-created_at")
                .limit(_TASK_HISTORY_LIMIT)
                .to_list()
            )

            if recent_tasks:
                task_lines = []
                for t in recent_tasks:
                    prompt_snippet = (t.prompt or "")[:80]
                    if len(t.prompt or "") > 80:
                        prompt_snippet += "…"
                    task_lines.append(
                        f"    <task>"
                        f"<prompt>{escape(prompt_snippet)}</prompt>"
                        f"<status>{escape(t.status)}</status>"
                        f"<created_at>{t.created_at.isoformat()}</created_at>"
                        f"</task>"
                    )
                parts.append(
                    "  <task_history>\n" + "\n".join(task_lines) + "\n  </task_history>"
                )
    except Exception as exc:
        logger.debug("chat_context: task_history failed: %s", exc)

    # ── 5. STM / LTM memories ────────────────────────────────────────────────
    try:
        memory_context = await _memory_manager.build_memory_context(str(agent.id))
        if memory_context:
            parts.append(f"  {memory_context.strip()}")
    except Exception as exc:
        logger.debug("chat_context: memory failed: %s", exc)

    parts.append("</agent_context>")
    return "\n".join(parts)
