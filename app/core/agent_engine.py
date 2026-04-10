"""Agent execution engine powered by the GitHub Copilot SDK.

Creates a Copilot SDK session per prompt execution, with the agent's
system prompt, model, MCP servers, and skills. The SDK handles the
agentic loop (planning, tool invocation, response generation) natively.

Capabilities wired:
- Infinite sessions with automatic context compaction
- Usage / cost / token tracking (assistant.usage + session.usage_info events)
- Hooks system (pre/post tool use, error recovery, session lifecycle)
- Streaming (assistant.message_delta events)
- Notion / Slack MCP auto-injection based on workflow output destinations
- Real-time SSE event publishing via event_bus
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime

from app.config import settings
from app.core import event_bus
from app.core.tool_registry import build_mcp_servers_config
from app.models.agent import Agent
from app.models.mcp_server import McpServer
from app.models.skill import Skill
from app.models.workflow import (
    LogEntry,
    Message,
    OutputFormat,
    UsageStats,
    Workflow,
    WorkflowStatus,
)
from app.services.copilot_client import build_client

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _log(workflow: Workflow, event: str, detail: str = "") -> None:
    """Append a log entry, persist to DB, and publish to SSE subscribers."""
    workflow.logs.append(LogEntry(event=event, detail=detail))
    workflow.updated_at = datetime.now(UTC)
    await workflow.save()
    await event_bus.publish(
        str(workflow.id),
        "log",
        {"event": event, "detail": detail},
    )


async def _publish_status(workflow: Workflow) -> None:
    """Publish a status change to SSE subscribers."""
    await event_bus.publish(
        str(workflow.id),
        "status",
        {"status": workflow.status, "current_turn": workflow.current_turn},
    )


async def _build_system_prompt(
    agent: Agent,
    skill_ids: list[str],
    workflow: Workflow,
) -> str:
    """Assemble the system prompt from agent config + skills + output destination hints."""
    system_prompt = agent.system_prompt

    # Skills
    if skill_ids:
        skill_sections: list[str] = []
        for sid in skill_ids:
            skill = await Skill.get(sid)
            if skill:
                skill_sections.append(
                    f'<skill name="{skill.name}">\n{skill.instructions}\n</skill>'
                )
        if skill_sections:
            system_prompt += "\n\n<skills>\n" + "\n".join(skill_sections) + "\n</skills>"

    # Output destination hints
    dest = workflow.output_destination
    if dest:
        hints: list[str] = []
        if dest.notion_base_page_id:
            if settings.notion_token:
                hints.append(
                    f"You have access to Notion. When producing document output, "
                    f"create a sub-page under page ID {dest.notion_base_page_id}."
                )
            else:
                hints.append(
                    "Notion output was requested but no Notion token is configured. "
                    "Skip Notion output."
                )
        if dest.slack_channel_id:
            if settings.slack_bot_token:
                hints.append(
                    f"You have access to Slack. Send output to channel {dest.slack_channel_id}."
                )
            else:
                hints.append(
                    "Slack output was requested but no Slack bot token is configured. "
                    "Skip Slack output."
                )
        elif dest.slack_user_id:
            if settings.slack_bot_token:
                hints.append(
                    f"You have access to Slack. Send output to user {dest.slack_user_id}."
                )
            else:
                hints.append(
                    "Slack output was requested but no Slack bot token is configured. "
                    "Skip Slack output."
                )
        if hints:
            system_prompt += (
                "\n\n<output_destinations>\n" + "\n".join(hints) + "\n</output_destinations>"
            )

    return system_prompt


def _build_dynamic_mcp_config(workflow: Workflow) -> dict:
    """Build MCP server configs for Notion/Slack based on workflow settings."""
    config: dict = {}
    dest = workflow.output_destination
    if not dest:
        return config

    # Notion MCP
    if dest.notion_base_page_id and settings.notion_token:
        headers_json = json.dumps({
            "Authorization": f"Bearer {settings.notion_token}",
            "Notion-Version": "2022-06-28",
        })
        env = dict(os.environ)
        env["OPENAPI_MCP_HEADERS"] = headers_json
        config["notion"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@notionhq/notion-mcp-server"],
            "env": env,
        }

    # Slack MCP
    if (dest.slack_channel_id or dest.slack_user_id) and settings.slack_bot_token:
        env = dict(os.environ)
        env["SLACK_BOT_TOKEN"] = settings.slack_bot_token
        config["slack"] = {
            "type": "stdio",
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": env,
        }

    return config


# ── Main Execution ───────────────────────────────────────────────────────────


async def run_agent(
    workflow: Workflow,
    user_prompt: str,
    github_token: str,
) -> str | None:
    """Execute a prompt using the GitHub Copilot SDK.

    1. Creates a CopilotClient with the caller's GitHub token.
    2. Builds session config (model, system prompt, MCP servers, hooks, infinite sessions).
    3. Creates a session, sends the prompt, and waits for completion.
    4. Logs every significant event to the workflow and publishes to SSE subscribers.
    5. Tracks usage/cost data from SDK events.
    """
    if workflow.status not in (WorkflowStatus.ACTIVE, WorkflowStatus.RUNNING):
        return None

    agent = await Agent.get(workflow.agent_id)
    if not agent:
        workflow.status = WorkflowStatus.FAILED
        await _log(workflow, "error", "Agent not found")
        await _publish_status(workflow)
        return None

    # Mark running
    workflow.status = WorkflowStatus.RUNNING
    await _log(workflow, "prompt_received", user_prompt[:200])
    await _publish_status(workflow)

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

    # Auto-inject Notion/Slack MCPs based on workflow output destinations
    dynamic_mcps = _build_dynamic_mcp_config(workflow)
    mcp_config.update(dynamic_mcps)

    await _log(
        workflow,
        "mcp_loaded",
        f"{len(mcp_config)} MCP server(s) configured: {list(mcp_config.keys())}",
    )

    # Build system prompt with skills + output destination hints
    system_prompt = await _build_system_prompt(agent, workflow.skill_ids, workflow)

    # ── Usage tracking state ──
    usage = UsageStats()

    # ── Tool call tracking for max-turns ──
    tool_call_count = 0
    max_turns = workflow.max_turns
    error_retry_counts: dict[str, int] = {}

    def permission_handler(request, invocation):
        """Auto-approve but enforce max tool-call turns."""
        nonlocal tool_call_count
        kind = request.get("kind", "") if isinstance(request, dict) else (
            request.kind.value if hasattr(request, "kind") and hasattr(request.kind, "value")
            else str(getattr(request, "kind", ""))
        )
        if kind in ("custom-tool", "mcp", "shell"):
            tool_call_count += 1
            if tool_call_count > max_turns:
                return {"kind": "denied-by-rules"}
        return {"kind": "approved"}

    # ── Hooks ──
    def on_pre_tool_use(input_data, context):
        """Log tool invocation; deny if max turns exceeded."""
        nonlocal tool_call_count
        tool_name = input_data.get("toolName", "unknown")
        tool_call_count += 1
        if tool_call_count > max_turns:
            asyncio.create_task(
                _log(workflow, "tool_denied", f"{tool_name} — max turns exceeded")
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Max turns exceeded"}
        asyncio.create_task(
            _log(workflow, "tool_call", str(tool_name))
        )
        return {"permissionDecision": "allow"}

    def on_post_tool_use(input_data, context):
        """Log tool result; inject goal reminder when deep into the run."""
        tool_name = input_data.get("toolName", "unknown")
        asyncio.create_task(
            _log(workflow, "tool_result", f"{tool_name} completed")
        )
        result = {}
        # Inject goal reminder when past 50% of max turns to reduce hallucination
        if tool_call_count > max_turns * 0.5:
            result["additionalContext"] = (
                f"Reminder: The original user request was: {user_prompt[:300]}"
            )
        return result

    def on_error_occurred(input_data, context):
        """Retry recoverable errors up to 2 times, abort otherwise."""
        error = input_data.get("error", "unknown")
        recoverable = input_data.get("recoverable", False)
        error_ctx = input_data.get("errorContext", "system")
        asyncio.create_task(
            _log(workflow, "error", f"[{error_ctx}] {error} (recoverable={recoverable})")
        )
        if recoverable:
            key = f"{error_ctx}:{error[:50]}"
            count = error_retry_counts.get(key, 0)
            if count < 2:
                error_retry_counts[key] = count + 1
                return {"errorHandling": "retry"}
        return {"errorHandling": "abort"}

    def on_session_end(input_data, context):
        """Log session end reason."""
        reason = input_data.get("reason", "unknown")
        asyncio.create_task(
            _log(workflow, "session_end", f"Reason: {reason}")
        )
        return None

    hooks = {
        "on_pre_tool_use": on_pre_tool_use,
        "on_post_tool_use": on_post_tool_use,
        "on_error_occurred": on_error_occurred,
        "on_session_end": on_session_end,
    }

    final_text: str | None = None

    try:
        client = build_client(github_token)

        async with client as c:
            # Build session kwargs
            session_kwargs: dict = {
                "on_permission_request": permission_handler,
                "hooks": hooks,
                "model": workflow.model,
                "streaming": True,
                "system_message": {
                    "mode": "append",
                    "content": system_prompt,
                },
            }
            if mcp_config:
                session_kwargs["mcp_servers"] = mcp_config

            # Infinite session config
            if workflow.infinite_session:
                session_kwargs["infinite_sessions"] = {
                    "enabled": True,
                    "background_compaction_threshold": 0.80,
                    "buffer_exhaustion_threshold": 0.95,
                }

            await _log(
                workflow,
                "session_creating",
                f"Model: {workflow.model}, MCP servers: {list(mcp_config.keys())}, "
                f"infinite_session: {workflow.infinite_session}",
            )

            async with await c.create_session(**session_kwargs) as session:
                workflow.session_id = session.session_id
                await workflow.save()

                done = asyncio.Event()
                assistant_messages: list[str] = []

                def on_event(event):
                    """Handle SDK session events — log, track usage, publish to SSE."""
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
                        asyncio.create_task(event_bus.publish(
                            str(workflow.id), "message",
                            {"role": "assistant", "content": content},
                        ))

                    elif ev_type == "assistant.message_delta":
                        delta = getattr(event.data, "delta_content", None) or ""
                        if delta:
                            asyncio.create_task(event_bus.publish(
                                str(workflow.id), "message_delta",
                                {"delta": delta},
                            ))

                    elif ev_type == "assistant.usage":
                        # Accumulate token/cost data
                        data = event.data
                        usage.total_input_tokens += int(
                            getattr(data, "input_tokens", 0) or 0
                        )
                        usage.total_output_tokens += int(
                            getattr(data, "output_tokens", 0) or 0
                        )
                        usage.total_cache_read_tokens += int(
                            getattr(data, "cache_read_tokens", 0) or 0
                        )
                        usage.total_cache_write_tokens += int(
                            getattr(data, "cache_write_tokens", 0) or 0
                        )
                        cost = getattr(data, "cost", None)
                        if cost:
                            usage.total_cost += float(cost)
                        asyncio.create_task(event_bus.publish(
                            str(workflow.id), "usage", usage.model_dump(),
                        ))

                    elif ev_type == "session.usage_info":
                        data = event.data
                        premium = getattr(data, "total_premium_requests", None)
                        if premium is not None:
                            usage.total_premium_requests = float(premium)
                        asyncio.create_task(event_bus.publish(
                            str(workflow.id), "usage", usage.model_dump(),
                        ))

                    elif ev_type == "tool.execution_start":
                        tool_name = getattr(event.data, "tool_name", "unknown")
                        asyncio.create_task(
                            _log(workflow, "tool_call", str(tool_name))
                        )

                    elif ev_type == "tool.execution_complete":
                        tool_name = getattr(event.data, "tool_name", "unknown")
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

                    elif ev_type == "session.compaction_start":
                        asyncio.create_task(
                            _log(workflow, "compaction_start", "Context compaction started")
                        )

                    elif ev_type == "session.compaction_complete":
                        asyncio.create_task(
                            _log(workflow, "compaction_complete", "Context compaction completed")
                        )

                session.on(on_event)

                await _log(
                    workflow,
                    "model_call",
                    f"Sending prompt to {workflow.model} via Copilot SDK",
                )
                await session.send({"prompt": user_prompt})

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
                    await _publish_status(workflow)
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

                # Persist usage stats
                workflow.usage = usage

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
                await _publish_status(workflow)

    except Exception as e:
        workflow.status = WorkflowStatus.FAILED
        await _log(workflow, "error", str(e))
        await _publish_status(workflow)
        logger.exception("Agent run failed for workflow %s", workflow.id)
        final_text = None

    return final_text
