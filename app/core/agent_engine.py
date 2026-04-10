"""Agent execution engine powered by the GitHub Copilot SDK.

Creates a Copilot SDK session per prompt execution, with the agent's
system prompt, model, MCP servers, and skills. The SDK handles the
agentic loop (planning, tool invocation, response generation) natively.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime

from copilot.session import PermissionHandler, PermissionRequestResult

from app.config import settings
from app.core.tool_registry import build_mcp_servers_config
from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.skill import Skill
from app.models.workflow import (
    LogEntry,
    Message,
    OutputFormat,
    Workflow,
    WorkflowStatus,
)
from app.services.copilot_client import build_client

logger = logging.getLogger(__name__)


async def _log(workflow: Workflow, event: str, detail: str = "") -> None:
    """Append a log entry and persist to DB."""
    workflow.logs.append(LogEntry(event=event, detail=detail))
    workflow.updated_at = datetime.now(UTC)
    await workflow.save()


async def _build_system_prompt(agent: Agent, skill_ids: list[str]) -> str:
    """Assemble the system prompt from agent config + installed skills."""
    system_prompt = agent.system_prompt
    if not skill_ids:
        return system_prompt

    skill_sections: list[str] = []
    for sid in skill_ids:
        skill = await Skill.get(sid)
        if skill:
            skill_sections.append(
                f'<skill name="{skill.name}">\n{skill.instructions}\n</skill>'
            )
    if skill_sections:
        system_prompt += "\n\n<skills>\n" + "\n".join(skill_sections) + "\n</skills>"
    return system_prompt


async def run_agent(
    workflow: Workflow,
    user_prompt: str,
    github_token: str,
) -> str | None:
    """Execute a prompt using the GitHub Copilot SDK.

    1. Creates a CopilotClient with the caller's GitHub token.
    2. Builds session config (model, system prompt, MCP servers).
    3. Creates a session, sends the prompt, and waits for completion.
    4. Logs every significant event to the workflow for polling visibility.
    """
    if workflow.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING):
        return None

    agent = await Agent.get(workflow.agent_id)
    if not agent:
        workflow.status = WorkflowStatus.FAILED
        await _log(workflow, "error", "Agent not found")
        return None

    # Mark running
    workflow.status = WorkflowStatus.RUNNING
    await _log(workflow, "prompt_received", user_prompt[:200])

    # Append user message
    workflow.messages.append(Message(role="user", content=user_prompt))
    await workflow.save()

    # Load MCP servers from DB
    mcp_servers_db: list[McpServer] = []
    for server_id in agent.mcp_server_ids:
        server = await McpServer.get(server_id)
        if server:
            mcp_servers_db.append(server)

    mcp_config = build_mcp_servers_config(mcp_servers_db)
    await _log(
        workflow,
        "mcp_loaded",
        f"{len(mcp_config)} MCP server(s) configured",
    )

    # Build system prompt with skills
    system_prompt = await _build_system_prompt(agent, workflow.skill_ids)

    # Track tool calls for max-turns enforcement
    tool_call_count = 0
    max_turns = workflow.max_turns

    def permission_handler(request, invocation):
        """Auto-approve but enforce max tool-call turns."""
        nonlocal tool_call_count
        kind = request.kind.value if hasattr(request.kind, "value") else str(request.kind)
        if kind in ("custom-tool", "mcp", "shell"):
            tool_call_count += 1
            if tool_call_count > max_turns:
                return PermissionRequestResult(kind="denied-by-rules")
        return PermissionRequestResult(kind="approved")

    final_text: str | None = None

    try:
        client = build_client(github_token)

        async with client as c:
            # Build session kwargs
            session_kwargs: dict = {
                "on_permission_request": permission_handler,
                "model": workflow.model,
                "system_message": {
                    "mode": "append",
                    "content": system_prompt,
                },
            }
            if mcp_config:
                session_kwargs["mcp_servers"] = mcp_config

            await _log(
                workflow,
                "session_creating",
                f"Model: {workflow.model}, MCP servers: {list(mcp_config.keys())}",
            )

            async with await c.create_session(**session_kwargs) as session:
                workflow.session_id = session.session_id
                await workflow.save()

                done = asyncio.Event()
                assistant_messages: list[str] = []

                def on_event(event):
                    """Handle SDK session events and log them to the workflow."""
                    ev_type = (
                        event.type.value
                        if hasattr(event.type, "value")
                        else str(event.type)
                    )

                    if ev_type == "assistant.message":
                        content = getattr(event.data, "content", None) or ""
                        assistant_messages.append(content)
                        asyncio.create_task(
                            _log(workflow, "model_response", content[:200])
                        )

                    elif ev_type == "tool.executionStart":
                        tool_name = getattr(event.data, "toolName", "unknown")
                        asyncio.create_task(
                            _log(workflow, "tool_call", str(tool_name))
                        )

                    elif ev_type == "tool.executionComplete":
                        tool_name = getattr(event.data, "toolName", "unknown")
                        asyncio.create_task(
                            _log(workflow, "tool_result", f"{tool_name} completed")
                        )

                    elif ev_type == "session.idle":
                        done.set()

                    elif ev_type == "session.error":
                        error_msg = getattr(event.data, "message", str(event.data))
                        asyncio.create_task(
                            _log(workflow, "error", error_msg)
                        )
                        done.set()

                session.on(on_event)

                await _log(
                    workflow,
                    "model_call",
                    f"Sending prompt to {workflow.model} via Copilot SDK",
                )
                await session.send(user_prompt)

                # Wait for the session to finish (idle or error)
                try:
                    await asyncio.wait_for(
                        done.wait(), timeout=settings.session_timeout
                    )
                except asyncio.TimeoutError:
                    workflow.status = WorkflowStatus.FAILED
                    await _log(
                        workflow,
                        "error",
                        f"Session timed out after {settings.session_timeout}s",
                    )
                    return None

                # Retrieve conversation history from the SDK session
                try:
                    all_events = await session.get_messages()
                    for ev in all_events:
                        ev_type = (
                            ev.type.value
                            if hasattr(ev.type, "value")
                            else str(ev.type)
                        )
                        if ev_type == "assistant.message":
                            workflow.messages.append(
                                Message(
                                    role="assistant",
                                    content=getattr(ev.data, "content", ""),
                                )
                            )
                except Exception as exc:
                    logger.warning("Failed to retrieve session messages: %s", exc)

                # Extract final response
                if assistant_messages:
                    final_text = assistant_messages[-1]

                workflow.current_turn = tool_call_count

                # Check if max turns was hit
                if tool_call_count > max_turns:
                    workflow.status = WorkflowStatus.MAX_TURNS_REACHED
                    await _log(workflow, "max_turns_reached", f"{tool_call_count} tool calls")
                elif workflow.status == WorkflowStatus.RUNNING:
                    workflow.status = WorkflowStatus.COMPLETED

                # Format output
                if final_text and workflow.output_format == OutputFormat.JSON:
                    final_text = json.dumps({"response": final_text})

                await _log(workflow, "completed", f"Final status: {workflow.status}")

    except Exception as e:
        workflow.status = WorkflowStatus.FAILED
        await _log(workflow, "error", str(e))
        logger.exception("Agent run failed for workflow %s", workflow.id)
        final_text = None

    return final_text

    return final_text
