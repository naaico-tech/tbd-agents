"""Agent execution engine powered by the GitHub Copilot SDK.

Creates a Copilot SDK session per prompt execution, with the agent's
system prompt, model, MCP servers, and skills. The SDK handles the
agentic loop (planning, tool invocation, response generation) natively.

Capabilities wired:
- Infinite sessions with automatic context compaction
- Usage / cost / token tracking (assistant.usage + session.usage_info events)
- Hooks system (pre/post tool use, error recovery, session lifecycle)
- Streaming (assistant.message_delta events)
- Tag-based MCP server resolution (agents select MCPs by ID and/or tags)
- Real-time SSE event publishing via event_bus
- BYOK (Bring Your Own Key) provider support via external LLM APIs
"""

import asyncio
import json
import logging
import os
from datetime import UTC, datetime

import httpx

from app.config import settings
from app.core import event_bus
from app.core.tool_registry import build_mcp_servers_config
from app.models.agent import Agent
from app.models.knowledge_source import KnowledgeSource
from app.models.mcp_server import McpServer
from app.models.provider import PROVIDER_DEFAULT_BASE_URLS, Provider, ProviderType
from app.models.skill import Skill
from app.models.task_execution import (
    TaskExecution,
    TaskProgress,
    TaskStatus,
    TodoItem,
    TodoItemStatus,
)
from app.models.workflow import (
    LogEntry,
    Message,
    OutputFormat,
    UsageStats,
    Workflow,
    WorkflowStatus,
)
from app.observability import (
    agent_task_duration_seconds,
    agent_tasks_active,
    agent_tasks_total,
    cost_dollars_total,
    cost_per_task_dollars,
    mcp_connections_total,
    premium_requests_total,
    repo_sync_duration_seconds,
    repo_sync_total,
    tokens_total,
    tool_calls_per_task,
    tool_calls_total,
)
from app.services import token_manager
from app.services.copilot_client import build_client
from app.services.knowledge_manager import knowledge_manager
from app.services.memory_manager import memory_manager

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _log(
    workflow: Workflow,
    event: str,
    detail: str = "",
    task_exec: TaskExecution | None = None,
    tool_input: str | None = None,
    tool_output: str | None = None,
) -> None:
    """Append a log entry, persist to DB, and publish to SSE subscribers."""
    entry = LogEntry(event=event, detail=detail, tool_input=tool_input, tool_output=tool_output)
    workflow.logs.append(entry)
    workflow.updated_at = datetime.now(UTC)
    await workflow.save()
    if task_exec:
        task_exec.logs.append(entry)
        await task_exec.save()
    payload: dict = {"event": event, "detail": detail}
    if tool_input is not None:
        payload["tool_input"] = tool_input
    if tool_output is not None:
        payload["tool_output"] = tool_output
    await event_bus.publish(
        str(workflow.id),
        "log",
        payload,
    )


async def _publish_status(workflow: Workflow, status: str | None = None) -> None:
    """Publish a status change to SSE subscribers."""
    await event_bus.publish(
        str(workflow.id),
        "status",
        {"status": status or "running", "current_turn": workflow.current_turn},
    )


def _parse_todo_list(args: dict | list | str) -> TaskProgress | None:
    """Parse a manage_todo_list tool call into a TaskProgress object."""
    try:
        if isinstance(args, str):
            args = json.loads(args)
        todo_list = args.get("todoList") if isinstance(args, dict) else None
        if not todo_list or not isinstance(todo_list, list):
            return None
        todos: list[TodoItem] = []
        current_step: int | None = None
        for item in todo_list:
            status_str = item.get("status", "not-started")
            try:
                status = TodoItemStatus(status_str)
            except ValueError:
                status = TodoItemStatus.NOT_STARTED
            todo = TodoItem(
                id=int(item.get("id", 0)),
                title=str(item.get("title", "")),
                status=status,
            )
            todos.append(todo)
            if status == TodoItemStatus.IN_PROGRESS:
                current_step = todo.id
        completed = sum(1 for t in todos if t.status == TodoItemStatus.COMPLETED)
        percent = completed / len(todos) if todos else 0.0
        return TaskProgress(
            todos=todos,
            current_step=current_step,
            percent_complete=round(percent, 2),
        )
    except Exception:
        return None


async def _update_progress(
    workflow: Workflow,
    task_exec: TaskExecution | None,
    progress: TaskProgress,
) -> None:
    """Persist progress to the task execution and publish to SSE."""
    if task_exec:
        task_exec.progress = progress
        await task_exec.save()
    await event_bus.publish(
        str(workflow.id),
        "progress",
        {
            "todos": [t.model_dump() for t in progress.todos],
            "current_step": progress.current_step,
            "percent_complete": progress.percent_complete,
        },
    )


async def _build_system_prompt(
    agent: Agent,
    skill_ids: list[str],
    workflow: Workflow,
    knowledge_context: str = "",
    memory_context: str = "",
) -> str:
    """Assemble the system prompt from agent config + skills + knowledge + memories."""
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

    # Knowledge
    if knowledge_context:
        system_prompt += "\n\n" + knowledge_context

    # Memories
    if memory_context:
        system_prompt += "\n\n" + memory_context

    # Autonomous execution directive
    system_prompt += (
        "\n\n<execution_policy>"
        "\nYou are running as an autonomous agent. You MUST act on your own using "
        "the tools and context available to you. NEVER ask the user follow-up questions, "
        "request clarification, or suggest that the user do something manually. "
        "If information is ambiguous or incomplete, make reasonable assumptions based on "
        "your system prompt and available tools, then proceed. Always produce a concrete, "
        "actionable result."
        "\n</execution_policy>"
    )

    return system_prompt


REPOS_BASE = "/repos"


async def _sync_repo(workflow: Workflow) -> str | None:
    """Clone or pull the workflow's configured repository.

    Returns the local path to the repo checkout, or None if no repo configured.
    Uses shallow clone (--depth 1) for speed.
    """
    if not workflow.repo_url:
        return None

    import hashlib
    import shlex

    repo_dir = os.path.join(
        REPOS_BASE,
        hashlib.sha256(f"{workflow.id}:{workflow.repo_url}".encode()).hexdigest()[:16],
    )
    branch = workflow.repo_branch or "main"

    # Build auth URL if a token name is configured
    clone_url = workflow.repo_url
    if workflow.repo_token_name:
        token_value = await token_manager.get_token_value(workflow.repo_token_name)
        if token_value:
            # Insert token into HTTPS URL: https://TOKEN@github.com/...
            clone_url = clone_url.replace("https://", f"https://{token_value}@")

    if os.path.isdir(os.path.join(repo_dir, ".git")):
        # Pull latest
        cmd = f"git -C {shlex.quote(repo_dir)} fetch --depth 1 origin {shlex.quote(branch)} && git -C {shlex.quote(repo_dir)} checkout FETCH_HEAD"
    else:
        os.makedirs(repo_dir, exist_ok=True)
        cmd = f"git clone --depth 1 --branch {shlex.quote(branch)} {shlex.quote(clone_url)} {shlex.quote(repo_dir)}"

    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Repo sync failed for %s: %s", workflow.repo_url, stderr.decode()[:500])
        return None

    return repo_dir


# ── BYOK Custom Provider Execution ───────────────────────────────────────────


def _build_provider_headers(provider: Provider, api_key: str) -> dict[str, str]:
    """Build HTTP headers for a provider request."""
    provider_type = provider.provider_type
    if provider_type == ProviderType.ANTHROPIC:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    elif provider_type == ProviderType.AZURE_OPENAI:
        return {
            "api-key": api_key,
            "content-type": "application/json",
        }
    else:
        return {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }


def _resolve_provider_url(provider: Provider) -> str:
    """Resolve the chat completions endpoint URL for a provider."""
    raw_url = provider.base_url or PROVIDER_DEFAULT_BASE_URLS.get(provider.provider_type)
    if raw_url is None:
        raise ValueError(
            f"Provider '{provider.name}' has no base_url configured and none is available "
            f"for provider_type '{provider.provider_type}'."
        )
    return raw_url.rstrip("/") + "/chat/completions"


def _mcp_tool_to_openai(tool) -> dict:
    """Convert an MCP Tool object to OpenAI function-calling tool format."""
    schema = dict(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}
    # Ensure the schema has type: object at the top level
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": schema,
        },
    }


async def _connect_mcp_and_list_tools(
    mcp_config: dict,
    allowed_tools_set: set[str] | None,
    exit_stack,
) -> tuple[list[dict], dict]:
    """Connect to MCP servers and list their tools.

    Returns ``(openai_tools, tool_server_map)`` where ``tool_server_map``
    maps tool names to ``(session, server_name)`` tuples for later invocation.

    The caller-provided ``exit_stack`` (``AsyncExitStack``) manages the
    lifetime of all MCP connections so they stay open for tool invocations.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    openai_tools: list[dict] = []
    tool_server_map: dict[str, tuple[ClientSession, str]] = {}

    for server_name, server_cfg in mcp_config.items():
        transport_type = server_cfg.get("type", "")

        try:
            if transport_type == "stdio":
                server_params = StdioServerParameters(
                    command=server_cfg["command"],
                    args=server_cfg.get("args", []),
                    env=server_cfg.get("env"),
                )
                # Use /dev/null for stderr to avoid Celery's LoggingProxy
                # which lacks fileno() needed by subprocess.
                devnull = open(os.devnull, "w")  # noqa: SIM115
                exit_stack.callback(devnull.close)
                streams = await exit_stack.enter_async_context(
                    stdio_client(server_params, errlog=devnull)
                )
                read_stream, write_stream = streams
            elif transport_type == "sse":
                url = server_cfg["url"]
                headers = server_cfg.get("headers", {})
                streams = await exit_stack.enter_async_context(
                    sse_client(url, headers=headers)
                )
                read_stream, write_stream = streams
            elif transport_type == "http":
                url = server_cfg["url"]
                headers = server_cfg.get("headers", {})
                streams = await exit_stack.enter_async_context(
                    streamablehttp_client(url, headers=headers)
                )
                read_stream, write_stream = streams[0], streams[1]
            else:
                continue

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            result = await session.list_tools()

            for tool in result.tools:
                # Respect allowed_tools filter
                if allowed_tools_set is not None and tool.name not in allowed_tools_set:
                    continue
                openai_tools.append(_mcp_tool_to_openai(tool))
                tool_server_map[tool.name] = (session, server_name)
        except Exception as exc:
            logger.warning("Failed to connect MCP server '%s' for BYOK tools: %s", server_name, exc)

    return openai_tools, tool_server_map


async def _handle_store_memory(agent_id: str, arguments: dict) -> str:
    """Handle the store_memory built-in tool call."""
    from app.models.memory import MemoryScope

    key = arguments.get("key", "")
    value = arguments.get("value", "")
    scope = arguments.get("scope", "agent")
    metadata = arguments.get("metadata", {})

    if not key or not value:
        return json.dumps({"error": "Both 'key' and 'value' are required"})

    try:
        scope_enum = MemoryScope(scope)
    except ValueError:
        return json.dumps({"error": f"Invalid scope '{scope}'. Use: session, agent, global"})

    mem = await memory_manager.store(
        agent_id=agent_id,
        scope=scope_enum,
        key=key,
        value=value,
        metadata=metadata,
    )
    return json.dumps({"status": "stored", "key": mem.key, "scope": mem.scope})


# OpenAI-format tool definition for store_memory
STORE_MEMORY_TOOL_OPENAI = {
    "type": "function",
    "function": {
        "name": "store_memory",
        "description": (
            "Save a key-value memory for future reference across conversations. "
            "Use this to remember important facts, decisions, user preferences, "
            "or context that should persist."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "A short descriptive key for the memory",
                },
                "value": {
                    "type": "string",
                    "description": "The content to remember",
                },
                "scope": {
                    "type": "string",
                    "enum": ["session", "agent", "global"],
                    "description": "Memory scope: session (this workflow), agent (this agent), global (all agents)",
                    "default": "agent",
                },
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata tags",
                },
            },
            "required": ["key", "value"],
        },
    },
}

# Claude-format tool definition for store_memory
STORE_MEMORY_TOOL_CLAUDE = {
    "type": "custom",
    "name": "store_memory",
    "description": (
        "Save a key-value memory for future reference across conversations. "
        "Use this to remember important facts, decisions, user preferences, "
        "or context that should persist."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "A short descriptive key for the memory",
            },
            "value": {
                "type": "string",
                "description": "The content to remember",
            },
            "scope": {
                "type": "string",
                "enum": ["session", "agent", "global"],
                "description": "Memory scope: session (this workflow), agent (this agent), global (all agents)",
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata tags",
            },
        },
        "required": ["key", "value"],
    },
}


async def _execute_mcp_tool(
    tool_name: str,
    arguments: dict,
    tool_server_map: dict,
) -> str:
    """Call a tool on its MCP server and return the text result."""
    entry = tool_server_map.get(tool_name)
    if not entry:
        return json.dumps({"error": f"Tool '{tool_name}' not found in any connected MCP server"})

    session, _server_name = entry
    try:
        result = await session.call_tool(tool_name, arguments)
        # Combine text content blocks
        parts = []
        for block in result.content:
            if hasattr(block, "text"):
                parts.append(block.text)
            elif hasattr(block, "data"):
                parts.append(f"[binary: {getattr(block, 'mimeType', 'unknown')}]")
        text = "\n".join(parts) if parts else ""
        if result.isError:
            return json.dumps({"error": text})
        return text
    except Exception as exc:
        return json.dumps({"error": f"Tool execution failed: {exc}"})


# ── Claude Agent SDK helpers ──────────────────────────────────────────────────


def _resolve_refs(obj, defs: dict):
    """Recursively resolve ``$ref`` pointers using *defs* and return a new object."""
    if isinstance(obj, dict):
        if "$ref" in obj:
            ref_path = obj["$ref"]  # e.g. "#/$defs/Foo"
            parts = ref_path.lstrip("#/").split("/")
            # Walk into defs: skip the leading "$defs" segment
            resolved = defs
            for part in parts:
                if part == "$defs":
                    continue
                resolved = resolved.get(part, {}) if isinstance(resolved, dict) else {}
            # Recursively resolve in case the definition itself has $ref
            return _resolve_refs(resolved, defs)
        return {k: _resolve_refs(v, defs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_refs(item, defs) for item in obj]
    return obj


_ALLOWED_SCHEMA_KEYS = {"type", "properties", "required", "description", "additionalProperties"}


def _mcp_tool_to_claude_custom(tool) -> dict:
    """Convert a local MCP Tool to a Claude Agent SDK custom tool definition.

    Used for stdio-based MCP servers whose tools must be handled locally
    via ``agent.custom_tool_use`` events.
    """
    schema = dict(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    # Claude API rejects $ref; resolve them against $defs before stripping.
    defs = schema.get("$defs", {})
    if defs:
        schema = _resolve_refs(schema, defs)
    # Keep only the keys the API accepts.
    schema = {k: v for k, v in schema.items() if k in _ALLOWED_SCHEMA_KEYS}
    return {
        "type": "custom",
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": schema,
    }


async def _connect_local_mcp_and_list_tools(
    mcp_config: dict,
    allowed_tools_set: set[str] | None,
    exit_stack,
) -> tuple[list[dict], dict]:
    """Connect to *local* (stdio) MCP servers and return Claude custom tool defs.

    Returns ``(custom_tools, tool_server_map)`` where:
    - ``custom_tools`` is a list of Claude Agent SDK custom tool params
    - ``tool_server_map`` maps tool names to ``(session, server_name)``
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    custom_tools: list[dict] = []
    tool_server_map: dict[str, tuple[ClientSession, str]] = {}

    for server_name, server_cfg in mcp_config.items():
        if server_cfg.get("type") != "stdio":
            continue

        try:
            server_params = StdioServerParameters(
                command=server_cfg["command"],
                args=server_cfg.get("args", []),
                env=server_cfg.get("env"),
            )
            devnull = open(os.devnull, "w")  # noqa: SIM115
            exit_stack.callback(devnull.close)
            streams = await exit_stack.enter_async_context(
                stdio_client(server_params, errlog=devnull)
            )
            read_stream, write_stream = streams

            session = await exit_stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()
            result = await session.list_tools()

            for tool in result.tools:
                if allowed_tools_set is not None and tool.name not in allowed_tools_set:
                    continue
                custom_tools.append(_mcp_tool_to_claude_custom(tool))
                tool_server_map[tool.name] = (session, server_name)
        except Exception as exc:
            logger.warning(
                "Failed to connect stdio MCP server '%s' for Claude Agent SDK: %s",
                server_name, exc,
            )

    return custom_tools, tool_server_map


def _build_claude_agent_mcp_servers(mcp_config: dict) -> list[dict]:
    """Build native Claude Agent SDK MCP server params for URL-based servers.

    Returns a list of ``{"type": "url", "name": ..., "url": ...}`` dicts
    for SSE and HTTP MCP servers that the Claude Agent SDK can connect to
    directly on Anthropic's infrastructure.
    """
    servers: list[dict] = []
    for server_name, server_cfg in mcp_config.items():
        transport = server_cfg.get("type", "")
        if transport in ("sse", "http"):
            url = server_cfg.get("url")
            if url:
                servers.append({"type": "url", "name": server_name, "url": url})
    return servers


# All tools available in the Claude Agent SDK agent_toolset_20260401
CLAUDE_AGENT_TOOLSET_TOOLS = [
    "bash", "read", "write", "edit", "glob", "grep", "web_fetch", "web_search",
]


def _build_claude_agent_tools(
    native_mcp_servers: list[dict],
    custom_tools: list[dict],
    builtin_tools: list[str] | None = None,
) -> list[dict]:
    """Assemble the full tools list for a Claude Agent SDK agent.

    Includes:
    - ``agent_toolset_20260401`` entry with per-tool enable/disable config
    - ``mcp_toolset`` entries for each native (URL-based) MCP server
    - ``custom`` tool entries for stdio-based MCP server tools
    """
    tools: list[dict] = []

    # ── Agent toolset (built-in tools) ────────────────────────────────────
    if builtin_tools:
        # Enable only the requested built-in tools
        toolset: dict = {
            "type": "agent_toolset_20260401",
            "default_config": {"enabled": False},
            "configs": [
                {"name": name, "enabled": True}
                for name in builtin_tools
                if name in CLAUDE_AGENT_TOOLSET_TOOLS
            ],
        }
        tools.append(toolset)

    for srv in native_mcp_servers:
        tools.append({"type": "mcp_toolset", "mcp_server_name": srv["name"]})
    tools.extend(custom_tools)
    return tools


async def _run_with_claude_sdk(
    workflow: Workflow,
    user_prompt: str,
    system_prompt: str,
    provider: Provider,
    api_key: str,
    task_exec: TaskExecution | None,
    *,
    mcp_config: dict | None = None,
    allowed_tools_set: set[str] | None = None,
    builtin_tools: list[str] | None = None,
) -> str | None:
    """Execute a prompt using the Claude Agent SDK (beta.agents/sessions).

    Creates an environment, agent, and session on Anthropic's infrastructure,
    then streams events. The Agent SDK handles the full agentic loop
    (planning, tool invocation, response generation) server-side — analogous
    to how the Copilot SDK path works.

    MCP server handling:
    - URL-based (SSE/HTTP) servers are passed as native MCP servers to the
      Claude Agent, which connects to them directly.
    - stdio-based servers are connected locally; their tools are registered
      as custom tools, and ``agent.custom_tool_use`` events are handled by
      calling the local MCP session.
    """
    from contextlib import AsyncExitStack

    from app.services.claude_client import build_claude_client

    model = workflow.model
    task_start_time = datetime.now(UTC)
    agent_tasks_active.inc()
    final_text: str | None = None
    tool_call_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0

    mcp_exit_stack = AsyncExitStack()
    await mcp_exit_stack.__aenter__()

    # Track created Agent SDK resources for cleanup
    claude_environment_id: str | None = None
    claude_agent_id: str | None = None
    claude_session_id: str | None = None

    try:
        client = build_claude_client(api_key)

        # ── Discover local (stdio) MCP tools ─────────────────────────────────
        custom_tools: list[dict] = []
        tool_server_map: dict = {}

        if mcp_config:
            custom_tools, tool_server_map = await _connect_local_mcp_and_list_tools(
                mcp_config, allowed_tools_set, mcp_exit_stack
            )
            if custom_tools:
                await _log(
                    workflow, "tools_discovered",
                    f"{len(custom_tools)} local tool(s): "
                    f"{[t['name'] for t in custom_tools]}"[:200],
                    task_exec,
                )

        # ── Build native MCP servers for URL-based transports ────────────────
        native_mcp_servers = _build_claude_agent_mcp_servers(mcp_config or {})
        if native_mcp_servers:
            await _log(
                workflow, "mcp_native",
                f"{len(native_mcp_servers)} native MCP server(s): "
                f"{[s['name'] for s in native_mcp_servers]}",
                task_exec,
            )

        # ── Build agent tools list ───────────────────────────────────────────
        # Add store_memory as a custom tool
        custom_tools.append(STORE_MEMORY_TOOL_CLAUDE)
        agent_tools = _build_claude_agent_tools(
            native_mcp_servers, custom_tools, builtin_tools=builtin_tools,
        )

        await _log(
            workflow, "model_call",
            f"Creating Claude Agent SDK session for {model} "
            f"(provider: '{provider.name}', tools: {len(agent_tools)}, "
            f"native_mcp: {len(native_mcp_servers)})",
            task_exec,
        )

        # ── Create environment ───────────────────────────────────────────────
        environment = await client.beta.environments.create(
            name=f"tbd-agents-wf-{workflow.id}",
        )
        claude_environment_id = environment.id
        await _log(workflow, "claude_env_created", environment.id, task_exec)

        # ── Create agent ─────────────────────────────────────────────────────
        agent_kwargs: dict = {
            "model": model,
            "name": f"tbd-agent-{workflow.agent_id}",
            "system": system_prompt,
        }
        if native_mcp_servers:
            agent_kwargs["mcp_servers"] = native_mcp_servers
        if agent_tools:
            agent_kwargs["tools"] = agent_tools

        claude_agent = await client.beta.agents.create(**agent_kwargs)
        claude_agent_id = claude_agent.id
        await _log(workflow, "claude_agent_created", claude_agent.id, task_exec)

        # ── Create session ───────────────────────────────────────────────────
        session = await client.beta.sessions.create(
            environment_id=environment.id,
            agent={
                "type": "agent",
                "id": claude_agent.id,
                "version": claude_agent.version,
            },
        )
        claude_session_id = session.id
        workflow.session_id = session.id
        await workflow.save()
        await _log(workflow, "claude_session_created", session.id, task_exec)

        # ── Send user message ────────────────────────────────────────────────
        await client.beta.sessions.events.send(
            session.id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": user_prompt}],
            }],
        )

        # ── Stream events ────────────────────────────────────────────────────
        assistant_messages: list[str] = []
        done = False

        while not done:
            stream = await client.beta.sessions.events.stream(session.id)
            async for event in stream:
                ev_type = event.type

                if ev_type == "agent.message":
                    # Collect text from content blocks
                    text_parts = []
                    for block in event.content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                    content = "".join(text_parts)
                    assistant_messages.append(content)
                    await event_bus.publish(
                        str(workflow.id), "message",
                        {"role": "assistant", "content": content},
                    )
                    await _log(workflow, "model_response", content[:200], task_exec)

                elif ev_type == "agent.thinking":
                    await _log(workflow, "thinking", "Agent is thinking...", task_exec)

                elif ev_type == "agent.custom_tool_use":
                    # Local MCP tool invocation — execute and send result back
                    tool_call_count += 1
                    tool_name = event.name
                    tool_args = dict(event.input) if event.input else {}
                    tool_use_id = event.id

                    await _log(
                        workflow, "tool_call", tool_name, task_exec,
                        tool_input=json.dumps(tool_args, default=str)[:500],
                    )
                    tool_calls_total.labels(tool_name=tool_name).inc()

                    # Execute — built-in memory tool or local MCP session
                    if tool_name == "store_memory":
                        tool_result = await _handle_store_memory(
                            workflow.agent_id, tool_args
                        )
                    else:
                        tool_result = await _execute_mcp_tool(
                            tool_name, tool_args, tool_server_map,
                        )
                    await _log(
                        workflow, "tool_result", f"{tool_name} completed", task_exec,
                        tool_output=tool_result[:500],
                    )

                    # Send result back to the Claude Agent SDK session
                    await client.beta.sessions.events.send(
                        session.id,
                        events=[{
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": tool_use_id,
                            "content": [{"type": "text", "text": tool_result}],
                        }],
                    )

                elif ev_type == "agent.mcp_tool_use":
                    # Native MCP tool (handled server-side) — just log
                    tool_call_count += 1
                    tool_name = event.name
                    mcp_server = event.mcp_server_name
                    tool_args = dict(event.input) if event.input else {}
                    await _log(
                        workflow, "tool_call",
                        f"{tool_name} (mcp:{mcp_server})", task_exec,
                        tool_input=json.dumps(tool_args, default=str)[:500],
                    )
                    tool_calls_total.labels(tool_name=tool_name).inc()

                elif ev_type == "agent.mcp_tool_result":
                    await _log(workflow, "tool_result", "MCP tool completed", task_exec)

                elif ev_type == "agent.tool_use":
                    tool_call_count += 1
                    tool_name = getattr(event, "name", "built-in")
                    await _log(workflow, "tool_call", f"{tool_name} (built-in)", task_exec)
                    tool_calls_total.labels(tool_name=str(tool_name)).inc()

                elif ev_type == "agent.tool_result":
                    await _log(workflow, "tool_result", "Built-in tool completed", task_exec)

                elif ev_type == "span.model_request_end":
                    # Track token usage
                    mu = event.model_usage
                    total_input_tokens += mu.input_tokens
                    total_output_tokens += mu.output_tokens
                    total_cache_read_tokens += mu.cache_read_input_tokens
                    total_cache_write_tokens += mu.cache_creation_input_tokens
                    tokens_total.labels(direction="input", model=model).inc(mu.input_tokens)
                    tokens_total.labels(direction="output", model=model).inc(mu.output_tokens)
                    if mu.cache_read_input_tokens:
                        tokens_total.labels(direction="cache_read", model=model).inc(
                            mu.cache_read_input_tokens
                        )
                    if mu.cache_creation_input_tokens:
                        tokens_total.labels(direction="cache_write", model=model).inc(
                            mu.cache_creation_input_tokens
                        )
                    await event_bus.publish(
                        str(workflow.id), "usage",
                        {
                            "total_input_tokens": total_input_tokens,
                            "total_output_tokens": total_output_tokens,
                            "total_cache_read_tokens": total_cache_read_tokens,
                            "total_cache_write_tokens": total_cache_write_tokens,
                        },
                    )

                elif ev_type == "agent.thread_context_compacted":
                    await _log(workflow, "compaction_complete", "Context compacted", task_exec)

                elif ev_type == "session.error":
                    error_obj = event.error
                    error_msg = getattr(error_obj, "message", str(error_obj))
                    await _log(workflow, "error", error_msg, task_exec)
                    done = True
                    break

                elif ev_type == "session.status_idle":
                    stop_reason = event.stop_reason
                    reason_type = getattr(stop_reason, "type", "unknown")
                    await _log(
                        workflow, "session_idle",
                        f"Stop reason: {reason_type}",
                        task_exec,
                    )
                    if reason_type == "end_turn":
                        done = True
                        break
                    elif reason_type == "requires_action":
                        # Session needs user input — continue streaming
                        pass
                    else:
                        done = True
                        break

            # Check halt signal between stream iterations
            if not done and await event_bus.check_halt(str(workflow.id)):
                await event_bus.clear_halt(str(workflow.id))
                await _log(workflow, "halted", "Execution halted by user", task_exec)
                await _publish_status(workflow, "halted")
                if task_exec:
                    task_exec.status = TaskStatus.HALTED
                    task_exec.finished_at = datetime.now(UTC)
                    task_exec.tool_calls = tool_call_count
                    await task_exec.save()
                await workflow.save()
                return None

        # ── Extract final response ───────────────────────────────────────────
        if assistant_messages:
            final_text = assistant_messages[-1]

        # ── Publish final message ────────────────────────────────────────────
        if final_text:
            await event_bus.publish(
                str(workflow.id), "message",
                {"role": "assistant", "content": final_text},
            )

        # ── Record usage & finalize ──────────────────────────────────────────
        usage = UsageStats(
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cache_read_tokens=total_cache_read_tokens,
            total_cache_write_tokens=total_cache_write_tokens,
        )
        workflow.usage = usage
        workflow.messages.append(Message(role="assistant", content=final_text or ""))
        workflow.current_turn = tool_call_count

        if final_text and workflow.output_format == OutputFormat.JSON:
            final_text = json.dumps({"response": final_text})

        if tool_call_count:
            tool_calls_per_task.labels(model=model).observe(tool_call_count)

        await _log(workflow, "completed", f"Final status: completed (tool_calls: {tool_call_count})", task_exec)
        await _publish_status(workflow, "completed")

        task_duration = (datetime.now(UTC) - task_start_time).total_seconds()
        agent_task_duration_seconds.labels(model=model, status="completed").observe(task_duration)

        if task_exec:
            task_exec.status = TaskStatus.COMPLETED
            task_exec.finished_at = datetime.now(UTC)
            task_exec.tool_calls = tool_call_count
            task_exec.response = final_text
            task_exec.usage = usage
            task_exec.messages = [m for m in workflow.messages if m.role == "assistant"][-20:]
            await task_exec.save()

        await workflow.save()

    except Exception as exc:
        await _log(workflow, "error", str(exc), task_exec)
        await _publish_status(workflow, "failed")
        logger.exception("Claude Agent SDK run failed for workflow %s", workflow.id)
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
    finally:
        # Clean up local MCP connections
        try:
            await mcp_exit_stack.__aexit__(None, None, None)
        except Exception:
            pass
        # Clean up Claude Agent SDK resources (best-effort)
        try:
            if claude_session_id:
                await client.beta.sessions.delete(claude_session_id)
            if claude_agent_id:
                await client.beta.agents.archive(claude_agent_id)
            if claude_environment_id:
                await client.beta.environments.delete(claude_environment_id)
        except Exception:
            logger.debug("Claude Agent SDK cleanup failed (non-critical)")
        agent_tasks_active.dec()
        agent_tasks_total.labels(
            status=task_exec.status if task_exec else "completed",
            model=model,
            reasoning_effort="default",
        ).inc()

    return final_text


async def _run_with_custom_provider(
    workflow: Workflow,
    user_prompt: str,
    system_prompt: str,
    provider: Provider,
    api_key: str,
    task_exec: TaskExecution | None,
    *,
    mcp_config: dict | None = None,
    allowed_tools_set: set[str] | None = None,
) -> str | None:
    """Execute a prompt against an external OpenAI-compatible LLM API.

    Used when the agent's attached provider is not ``github_copilot``.
    Supports an agentic tool-call loop: if MCP servers are configured,
    their tools are discovered and provided to the model. When the model
    returns tool_calls, they are executed via MCP and results fed back
    until the model produces a final text response or max_turns is reached.
    """
    model = workflow.model
    max_turns = workflow.max_turns
    task_start_time = datetime.now(UTC)
    agent_tasks_active.inc()
    final_text: str | None = None
    tool_call_count = 0
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        from contextlib import AsyncExitStack
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.__aenter__()

        url = _resolve_provider_url(provider)
        headers = _build_provider_headers(provider, api_key)

        # Build conversation messages
        messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # ── Discover MCP tools ───────────────────────────────────────────────
        openai_tools: list[dict] = []
        tool_server_map: dict = {}

        if mcp_config:
            openai_tools, tool_server_map = await _connect_mcp_and_list_tools(
                mcp_config, allowed_tools_set, mcp_exit_stack
            )
            if openai_tools:
                await _log(
                    workflow,
                    "tools_discovered",
                    f"{len(openai_tools)} tool(s) available: {[t['function']['name'] for t in openai_tools]}"[:200],
                    task_exec,
                )

        # Always add the store_memory built-in tool
        openai_tools.append(STORE_MEMORY_TOOL_OPENAI)

        await _log(
            workflow,
            "model_call",
            f"Sending prompt to {model} via {provider.provider_type} provider '{provider.name}'"
            f" (tools: {len(openai_tools)})",
            task_exec,
        )

        # ── Agentic loop ────────────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=settings.session_timeout) as http:
            while True:
                body: dict = {"model": model, "messages": messages}
                if openai_tools:
                    body["tools"] = openai_tools
                    body["tool_choice"] = "auto"

                response = await http.post(url, headers=headers, json=body)
                response.raise_for_status()

                data = response.json()

                # Track token usage
                usage_data = data.get("usage", {})
                total_input_tokens += int(usage_data.get("prompt_tokens", 0))
                total_output_tokens += int(usage_data.get("completion_tokens", 0))

                choices = data.get("choices") or []
                if not choices:
                    break

                choice = choices[0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "")

                # ── Handle tool calls ────────────────────────────────────────
                tool_calls = message.get("tool_calls")
                if tool_calls and finish_reason != "stop":
                    # Append assistant message with tool_calls to conversation
                    messages.append(message)

                    for tc in tool_calls:
                        tool_call_count += 1
                        func = tc.get("function", {})
                        tool_name = func.get("name", "unknown")
                        raw_args = func.get("arguments", "{}")
                        try:
                            tool_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        except json.JSONDecodeError:
                            tool_args = {}

                        await _log(
                            workflow, "tool_call", tool_name, task_exec,
                            tool_input=json.dumps(tool_args)[:500],
                        )

                        # Execute the tool — built-in memory or MCP
                        if tool_name == "store_memory":
                            tool_result = await _handle_store_memory(
                                workflow.agent_id, tool_args
                            )
                        else:
                            tool_result = await _execute_mcp_tool(
                                tool_name, tool_args, tool_server_map
                            )

                        await _log(
                            workflow, "tool_result", f"{tool_name} completed", task_exec,
                            tool_output=tool_result[:500],
                        )

                        # Append tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": tool_result,
                        })

                    # Check max turns
                    if tool_call_count >= max_turns:
                        await _log(
                            workflow, "max_turns",
                            f"Reached max tool turns ({max_turns}), requesting final answer",
                            task_exec,
                        )
                        # Ask model for a final answer without tools
                        messages.append({
                            "role": "user",
                            "content": "You have reached the maximum number of tool calls. "
                            "Please provide your final answer based on the information gathered so far.",
                        })
                        final_body = {"model": model, "messages": messages}
                        final_resp = await http.post(url, headers=headers, json=final_body)
                        final_resp.raise_for_status()
                        final_data = final_resp.json()
                        fu = final_data.get("usage", {})
                        total_input_tokens += int(fu.get("prompt_tokens", 0))
                        total_output_tokens += int(fu.get("completion_tokens", 0))
                        fc = final_data.get("choices") or []
                        if fc:
                            final_text = fc[0].get("message", {}).get("content") or ""
                        break

                    # Continue the loop for the next model call
                    continue

                # ── Final text response (no tool calls) ──────────────────────
                final_text = message.get("content") or ""
                break

        # ── Record usage & finalize ──────────────────────────────────────────
        usage = UsageStats(
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
        )
        workflow.usage = usage
        if total_input_tokens:
            tokens_total.labels(direction="input", model=model).inc(total_input_tokens)
        if total_output_tokens:
            tokens_total.labels(direction="output", model=model).inc(total_output_tokens)
        if tool_call_count:
            tool_calls_total.labels(tool_name="byok_aggregate").inc(tool_call_count)

        workflow.messages.append(Message(role="assistant", content=final_text or ""))

        # Format output
        if final_text and workflow.output_format == OutputFormat.JSON:
            final_text = json.dumps({"response": final_text})

        await _log(workflow, "model_response", (final_text or "")[:200], task_exec)
        await _log(
            workflow, "completed",
            f"Final status: completed (tool_calls: {tool_call_count})",
            task_exec,
        )
        await _publish_status(workflow, "completed")

        task_duration = (datetime.now(UTC) - task_start_time).total_seconds()
        agent_task_duration_seconds.labels(
            model=model, status="completed"
        ).observe(task_duration)

        if task_exec:
            task_exec.status = TaskStatus.COMPLETED
            task_exec.finished_at = datetime.now(UTC)
            task_exec.tool_calls = tool_call_count
            task_exec.response = final_text
            task_exec.usage = usage
            task_exec.messages = [m for m in workflow.messages if m.role == "assistant"][-20:]
            await task_exec.save()

        await workflow.save()

    except httpx.HTTPStatusError as exc:
        await _log(
            workflow,
            "error",
            f"Provider HTTP error {exc.response.status_code}: {exc.response.text[:500]}",
            task_exec,
        )
        await _publish_status(workflow, "failed")
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
    except Exception as exc:
        await _log(workflow, "error", str(exc), task_exec)
        await _publish_status(workflow, "failed")
        logger.exception("Custom provider run failed for workflow %s", workflow.id)
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
    finally:
        # Close MCP server connections
        try:
            await mcp_exit_stack.__aexit__(None, None, None)
        except Exception:
            pass
        agent_tasks_active.dec()
        agent_tasks_total.labels(
            status=task_exec.status if task_exec else "completed",
            model=model,
            reasoning_effort="default",
        ).inc()

    return final_text


# ── Main Execution ───────────────────────────────────────────────────────────


async def run_agent(
    workflow: Workflow,
    user_prompt: str,
    github_token: str,
    task_execution_id: str | None = None,
    reasoning_effort: str | None = None,
) -> str | None:
    """Execute a prompt using the GitHub Copilot SDK or a BYOK custom provider.

    1. Resolves the agent's attached provider (if any):
       - ``github_copilot``: uses the stored token as the GitHub PAT.
       - All other types: routes to ``_run_with_custom_provider`` for direct
         HTTP execution against the provider's OpenAI-compatible API.
    2. Creates a CopilotClient with the resolved GitHub token (default path).
    3. Builds session config (model, system prompt, MCP servers, hooks, infinite sessions).
    4. Creates a session, sends the prompt, and waits for completion.
    5. Logs every significant event to the workflow and publishes to SSE subscribers.
    6. Tracks usage/cost data from SDK events.
    """
    # Load task execution if provided
    task_exec: TaskExecution | None = None
    if task_execution_id:
        from beanie import PydanticObjectId
        task_exec = await TaskExecution.get(PydanticObjectId(task_execution_id))
        if task_exec:
            task_exec.status = TaskStatus.RUNNING
            task_exec.started_at = datetime.now(UTC)
            task_exec.model = workflow.model
            await task_exec.save()

    if workflow.status != WorkflowStatus.ACTIVE:
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        return None

    agent = await Agent.get(workflow.agent_id)
    if not agent:
        await _log(workflow, "error", "Agent not found", task_exec)
        await _publish_status(workflow, "failed")
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        return None

    # ── BYOK provider resolution ──────────────────────────────────────────────
    # If the agent has a provider attached, resolve its API key and determine
    # the execution path (SDK vs direct HTTP).
    custom_provider: Provider | None = None
    custom_provider_key: str | None = None

    if agent.provider_id:
        try:
            from beanie import PydanticObjectId as _ObjId
            provider = await Provider.get(_ObjId(agent.provider_id))
        except Exception as _exc:
            logger.warning(
                "Failed to resolve provider_id '%s': %s", agent.provider_id, _exc
            )
            provider = None
        if provider:
            resolved_key = await token_manager.get_token_value(provider.api_key_token_name)
            if resolved_key:
                if provider.provider_type == ProviderType.GITHUB_COPILOT:
                    # Override the caller-supplied GitHub token with the stored one
                    github_token = resolved_key
                    await _log(
                        workflow,
                        "provider_resolved",
                        f"Using BYOK github_copilot provider '{provider.name}'",
                        task_exec,
                    )
                else:
                    custom_provider = provider
                    custom_provider_key = resolved_key
                    await _log(
                        workflow,
                        "provider_resolved",
                        f"Using BYOK provider '{provider.name}' ({provider.provider_type})",
                        task_exec,
                    )
            else:
                await _log(
                    workflow,
                    "provider_warning",
                    f"Provider '{provider.name}' token '{provider.api_key_token_name}' "
                    "not found in token store — falling back to default execution",
                    task_exec,
                )
        else:
            await _log(
                workflow,
                "provider_warning",
                f"Provider ID '{agent.provider_id}' not found — falling back to default execution",
                task_exec,
            )

    # Log prompt and publish running status for SSE
    await _log(workflow, "prompt_received", user_prompt[:200], task_exec)
    await _publish_status(workflow, "running")

    # Append user message
    workflow.messages.append(Message(role="user", content=user_prompt))
    await workflow.save()

    # Load MCP servers from DB — by explicit IDs and by tags (union, deduplicated)
    mcp_servers_map: dict[str, McpServer] = {}
    for server_id in agent.mcp_server_ids:
        server = await McpServer.get(server_id)
        if server:
            mcp_servers_map[str(server.id)] = server

    if agent.mcp_server_tags:
        tag_matches = await McpServer.find(
            {"tags": {"$in": agent.mcp_server_tags}},
        ).to_list()
        for server in tag_matches:
            mcp_servers_map[str(server.id)] = server

    mcp_servers_db: list[McpServer] = list(mcp_servers_map.values())

    mcp_config = await build_mcp_servers_config(mcp_servers_db)

    # Record MCP connection metrics
    for server_name in mcp_config:
        mcp_connections_total.labels(server_name=server_name).inc()

    # Build allowed-tools set for filtering in hooks.
    # If a server has a non-empty allowed_tools list, only those tools are permitted.
    # Tools from MCPs with no restrictions (empty list) are always allowed.
    allowed_tools_set: set[str] | None = None  # None = no filtering
    has_restrictions = any(s.allowed_tools for s in mcp_servers_db)
    if has_restrictions:
        allowed_tools_set = set()
        for s in mcp_servers_db:
            if s.allowed_tools:
                allowed_tools_set.update(s.allowed_tools)
            else:
                # Server has no restrictions – we can't enumerate its tools ahead of
                # time, so we mark it as unrestricted by adding a sentinel.
                allowed_tools_set = None
                break

    await _log(
        workflow,
        "mcp_loaded",
        f"{len(mcp_config)} MCP server(s) configured: {list(mcp_config.keys())}",
        task_exec,
    )

    # Build system prompt with skills + output destination hints
    # Resolve knowledge sources — by explicit IDs and by tags (union, deduplicated)
    from beanie import PydanticObjectId as _KsObjId

    knowledge_sources_map: dict[str, KnowledgeSource] = {}
    for ks_id in agent.knowledge_source_ids:
        try:
            ks = await KnowledgeSource.get(_KsObjId(ks_id))
        except Exception:
            logger.warning("Skipping invalid knowledge_source_id: %s", ks_id)
            continue
        if ks:
            knowledge_sources_map[str(ks.id)] = ks
    if agent.knowledge_tags:
        tag_ks = await KnowledgeSource.find(
            {"tags": {"$in": agent.knowledge_tags}},
        ).to_list()
        for ks in tag_ks:
            knowledge_sources_map[str(ks.id)] = ks

    knowledge_context = ""
    knowledge_sources_list = list(knowledge_sources_map.values())
    if knowledge_sources_list or agent.knowledge_tags:
        knowledge_context = await knowledge_manager.build_knowledge_context(
            knowledge_sources_list, agent.knowledge_tags
        )
        if knowledge_context:
            await _log(
                workflow,
                "knowledge_loaded",
                f"{len(knowledge_sources_list)} knowledge source(s) resolved",
                task_exec,
            )

    # ── Memory context ───────────────────────────────────────────────────────
    memory_context = ""
    if getattr(workflow, "bypass_memory", False):
        await _log(
            workflow,
            "memories_skipped",
            "Memory injection bypassed (workflow setting)",
            task_exec,
        )
    else:
        try:
            memory_context = await memory_manager.build_memory_context(
                agent_id=str(agent.id),
                workflow_id=str(workflow.id),
            )
            if memory_context:
                await _log(
                    workflow,
                    "memories_loaded",
                    "Agent memories injected into context",
                    task_exec,
                )
        except Exception as exc:
            logger.warning("Failed to load memories for agent %s: %s", agent.id, exc)

    system_prompt = await _build_system_prompt(
        agent, workflow.skill_ids, workflow, knowledge_context, memory_context
    )

    # Sync repository if configured
    repo_path = await _sync_repo(workflow)
    if repo_path:
        repo_sync_total.labels(status="success").inc()
        await _log(workflow, "repo_synced", f"Repository synced to {repo_path}", task_exec)
        system_prompt += (
            f"\n\n<repository>\n"
            f"A git repository has been cloned and is available at: {repo_path}\n"
            f"URL: {workflow.repo_url}\n"
            f"Branch: {workflow.repo_branch or 'main'}\n"
            f"You can read files from this path to understand the codebase.\n"
            f"</repository>"
        )
    elif workflow.repo_url:
        repo_sync_total.labels(status="failure").inc()
        await _log(workflow, "repo_sync_failed", f"Failed to sync {workflow.repo_url}", task_exec)

    # ── Route to custom provider if set ──────────────────────────────────────
    if custom_provider and custom_provider_key:
        # Use native Claude SDK for Anthropic providers
        if custom_provider.provider_type == ProviderType.ANTHROPIC:
            return await _run_with_claude_sdk(
                workflow,
                user_prompt,
                system_prompt,
                custom_provider,
                custom_provider_key,
                task_exec,
                mcp_config=mcp_config,
                allowed_tools_set=allowed_tools_set,
                builtin_tools=agent.builtin_tools or None,
            )
        return await _run_with_custom_provider(
            workflow,
            user_prompt,
            system_prompt,
            custom_provider,
            custom_provider_key,
            task_exec,
            mcp_config=mcp_config,
            allowed_tools_set=allowed_tools_set,
        )

    # ── Usage tracking state ──
    usage = UsageStats()
    task_start_time = datetime.now(UTC)
    agent_tasks_active.inc()

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
        """Log tool invocation; deny if max turns exceeded or tool not allowed."""
        nonlocal tool_call_count
        tool_name = input_data.get("toolName", "unknown")
        # Enforce allowed-tools filter
        if allowed_tools_set is not None and tool_name not in allowed_tools_set:
            asyncio.create_task(
                _log(workflow, "tool_denied", f"{tool_name} — not in allowed tools", task_exec)
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Tool not in allowed list"}
        tool_call_count += 1
        if tool_call_count > max_turns:
            asyncio.create_task(
                _log(workflow, "tool_denied", f"{tool_name} — max turns exceeded", task_exec)
            )
            return {"permissionDecision": "deny", "permissionDecisionReason": "Max turns exceeded"}
        asyncio.create_task(
            _log(workflow, "tool_call", str(tool_name), task_exec)
        )
        return {"permissionDecision": "allow"}

    def on_post_tool_use(input_data, context):
        """Log tool result; inject goal reminder when deep into the run."""
        tool_name = input_data.get("toolName", "unknown")
        asyncio.create_task(
            _log(workflow, "tool_result", f"{tool_name} completed", task_exec)
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
            _log(workflow, "error", f"[{error_ctx}] {error} (recoverable={recoverable})", task_exec)
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
            _log(workflow, "session_end", f"Reason: {reason}", task_exec)
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
                task_exec,
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
                            _log(workflow, "model_response", content[:200], task_exec)
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
                        input_tok = int(getattr(data, "input_tokens", 0) or 0)
                        output_tok = int(getattr(data, "output_tokens", 0) or 0)
                        cache_read = int(getattr(data, "cache_read_tokens", 0) or 0)
                        cache_write = int(getattr(data, "cache_write_tokens", 0) or 0)
                        usage.total_input_tokens += input_tok
                        usage.total_output_tokens += output_tok
                        usage.total_cache_read_tokens += cache_read
                        usage.total_cache_write_tokens += cache_write
                        cost = getattr(data, "cost", None)
                        if cost:
                            usage.total_cost += float(cost)
                        # Prometheus metrics
                        model = workflow.model
                        if input_tok:
                            tokens_total.labels(direction="input", model=model).inc(input_tok)
                        if output_tok:
                            tokens_total.labels(direction="output", model=model).inc(output_tok)
                        if cache_read:
                            tokens_total.labels(direction="cache_read", model=model).inc(cache_read)
                        if cache_write:
                            tokens_total.labels(direction="cache_write", model=model).inc(cache_write)
                        if cost:
                            cost_dollars_total.labels(model=model).inc(float(cost))
                        asyncio.create_task(event_bus.publish(
                            str(workflow.id), "usage", usage.model_dump(),
                        ))

                    elif ev_type == "session.usage_info":
                        data = event.data
                        premium = getattr(data, "total_premium_requests", None)
                        if premium is not None:
                            delta = float(premium) - usage.total_premium_requests
                            usage.total_premium_requests = float(premium)
                            if delta > 0:
                                premium_requests_total.labels(model=workflow.model).inc(delta)
                        asyncio.create_task(event_bus.publish(
                            str(workflow.id), "usage", usage.model_dump(),
                        ))

                    elif ev_type == "tool.execution_start":
                        data = event.data
                        tool_name = getattr(data, "tool_name", "unknown")
                        tool_calls_total.labels(tool_name=str(tool_name)).inc()
                        # Capture tool arguments
                        args_raw = getattr(data, "arguments", None)
                        tool_input_str = None
                        if args_raw is not None:
                            try:
                                tool_input_str = json.dumps(args_raw, indent=2, default=str) if isinstance(args_raw, (dict, list)) else str(args_raw)
                            except Exception:
                                tool_input_str = str(args_raw)
                        # Parse TODO progress from manage_todo_list calls
                        if str(tool_name) == "manage_todo_list" and args_raw is not None:
                            progress = _parse_todo_list(args_raw)
                            if progress:
                                asyncio.create_task(
                                    _update_progress(workflow, task_exec, progress)
                                )
                        mcp_server = getattr(data, "mcp_server_name", None)
                        detail = f"{tool_name}" + (f" (mcp:{mcp_server})" if mcp_server else "")
                        asyncio.create_task(
                            _log(workflow, "tool_call", detail, task_exec, tool_input=tool_input_str)
                        )

                    elif ev_type == "tool.execution_complete":
                        data = event.data
                        tool_name = getattr(data, "tool_name", "unknown")
                        success = getattr(data, "success", None)
                        # Capture tool result
                        result_obj = getattr(data, "result", None)
                        tool_output_str = None
                        if result_obj is not None:
                            detailed = getattr(result_obj, "detailed_content", None)
                            content = getattr(result_obj, "content", None)
                            tool_output_str = detailed or content
                        # Include error if present
                        error = getattr(data, "error", None) or getattr(data, "message", None)
                        if error and not tool_output_str:
                            tool_output_str = str(error)
                        status_tag = "completed" if success is not False else "FAILED"
                        asyncio.create_task(
                            _log(workflow, "tool_result", f"{tool_name} {status_tag}", task_exec, tool_output=tool_output_str)
                        )

                    elif ev_type == "session.idle":
                        done.set()

                    elif ev_type == "session.error":
                        error_msg = getattr(event.data, "message", str(event.data))
                        asyncio.create_task(
                            _log(workflow, "error", error_msg, task_exec)
                        )
                        done.set()

                    elif ev_type == "session.compaction_start":
                        asyncio.create_task(
                            _log(workflow, "compaction_start", "Context compaction started", task_exec)
                        )

                    elif ev_type == "session.compaction_complete":
                        asyncio.create_task(
                            _log(workflow, "compaction_complete", "Context compaction completed", task_exec)
                        )

                session.on(on_event)

                await _log(
                    workflow,
                    "model_call",
                    f"Sending prompt to {workflow.model} via Copilot SDK",
                    task_exec,
                )
                # Call RPC directly to avoid the SDK sending null values
                # for 'mode' and 'attachments' which causes "t.asString is
                # not a function" in the Node binary.
                send_params: dict = {"sessionId": session.session_id, "prompt": user_prompt}
                if reasoning_effort:
                    send_params["reasoningEffort"] = reasoning_effort
                await session._client.request("session.send", send_params)

                # Wait for the session to finish (idle or error)
                # Poll for halt signal every 2 seconds while waiting.
                try:
                    deadline = asyncio.get_event_loop().time() + settings.session_timeout
                    while not done.is_set():
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            raise asyncio.TimeoutError()
                        try:
                            await asyncio.wait_for(done.wait(), timeout=min(2.0, remaining))
                        except asyncio.TimeoutError:
                            if done.is_set():
                                break
                            # Check if user requested halt
                            if await event_bus.check_halt(str(workflow.id)):
                                await event_bus.clear_halt(str(workflow.id))
                                await session.abort()
                                workflow.current_turn = tool_call_count
                                await _log(workflow, "halted", "Execution halted by user", task_exec)
                                await _publish_status(workflow, "halted")
                                if task_exec:
                                    task_exec.status = TaskStatus.HALTED
                                    task_exec.finished_at = datetime.now(UTC)
                                    task_exec.tool_calls = tool_call_count
                                    await task_exec.save()
                                await workflow.save()
                                return None
                            # Not halted yet and not timed out — keep waiting
                            if remaining <= 2.0:
                                raise
                except asyncio.TimeoutError:
                    workflow.current_turn = tool_call_count
                    await _log(
                        workflow,
                        "error",
                        f"Session timed out after {settings.session_timeout}s",
                        task_exec,
                    )
                    await _publish_status(workflow, "failed")
                    if task_exec:
                        task_exec.status = TaskStatus.FAILED
                        task_exec.finished_at = datetime.now(UTC)
                        task_exec.tool_calls = tool_call_count
                        await task_exec.save()
                    await workflow.save()
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

                # ── Record task-level Prometheus metrics ──
                task_duration = (datetime.now(UTC) - task_start_time).total_seconds()

                # Determine task terminal status
                if tool_call_count > max_turns:
                    task_final_status = TaskStatus.MAX_TURNS_REACHED
                    await _log(workflow, "max_turns_reached", f"{tool_call_count} tool calls", task_exec)
                else:
                    task_final_status = TaskStatus.COMPLETED

                agent_task_duration_seconds.labels(
                    model=workflow.model, status=task_final_status,
                ).observe(task_duration)
                tool_calls_per_task.labels(model=workflow.model).observe(tool_call_count)
                if usage.total_cost > 0:
                    cost_per_task_dollars.labels(model=workflow.model).observe(usage.total_cost)

                # Format output
                if final_text and workflow.output_format == OutputFormat.JSON:
                    final_text = json.dumps({"response": final_text})

                await _log(workflow, "completed", f"Final status: {task_final_status}", task_exec)
                await _publish_status(workflow, task_final_status)

                # Finalize task execution
                if task_exec:
                    task_exec.status = task_final_status
                    task_exec.finished_at = datetime.now(UTC)
                    task_exec.tool_calls = tool_call_count
                    task_exec.response = final_text
                    task_exec.usage = usage
                    # Copy messages added during this execution
                    task_exec.messages = [
                        m for m in workflow.messages
                        if m.content == user_prompt or m.role == "assistant"
                    ][-20:]  # Keep last 20 messages for this execution
                    await task_exec.save()

                await workflow.save()

    except Exception as e:
        await _log(workflow, "error", str(e), task_exec)
        await _publish_status(workflow, "failed")
        logger.exception("Agent run failed for workflow %s", workflow.id)
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
    finally:
        agent_tasks_active.dec()
        agent_tasks_total.labels(
            status=task_exec.status if task_exec else "completed",
            model=workflow.model,
            reasoning_effort=reasoning_effort or "default",
        ).inc()

    return final_text
