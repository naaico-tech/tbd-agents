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
import csv
import html
import json
import logging
import os
import re
import sys
from io import StringIO
from datetime import datetime, timezone
from urllib.parse import urlparse

# Compatibility: UTC alias for Python 3.9-3.10 support
UTC = timezone.utc

import httpx

from app.config import settings
from app.core import event_bus
from app.core.guardrails import enforce_output_guardrails
from app.core.tool_registry import build_mcp_servers_config
from app.models.agent import Agent
from app.models.custom_tool import CustomTool
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
    context_compaction_messages_dropped,
    context_compactions_total,
    cost_dollars_total,
    cost_per_task_dollars,
    mcp_connections_total,
    premium_requests_total,
    repo_sync_total,
    tokens_total,
    tool_calls_per_task,
    tool_calls_total,
)
from app.services import custom_tool_runner, token_manager
from app.services.copilot_client import build_client
from app.services.knowledge_manager import knowledge_manager
from app.services.memory_manager import memory_manager
from app.services.token_counter import count_tokens, estimate_messages_tokens

logger = logging.getLogger(__name__)

_CAVEMAN_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_CAVEMAN_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")
_CAVEMAN_PROTECTED_RE = re.compile(
    r"(```.*?```|`[^`]+`|https?://\S+|(?:\./|/)?[\w./-]+\.[A-Za-z0-9_-]+|&[a-zA-Z#0-9]+;)",
    re.DOTALL,
)
_CAVEMAN_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "for", "from",
    "has", "have", "in", "into", "is", "it", "of", "on", "or", "that", "the",
    "their", "there", "this", "to", "was", "were", "will", "with", "you", "your",
}
_CAVEMAN_REPLACEMENTS = (
    (re.compile(r"\bplease\b", re.IGNORECASE), ""),
    (re.compile(r"\bkindly\b", re.IGNORECASE), ""),
    (re.compile(r"\b(make sure|ensure) to\b", re.IGNORECASE), ""),
    (re.compile(r"\bit is important to\b", re.IGNORECASE), ""),
    (re.compile(r"\bin order to\b", re.IGNORECASE), "to"),
    (re.compile(r"\byou should\b", re.IGNORECASE), ""),
    (re.compile(r"\bi would recommend\b", re.IGNORECASE), "use"),
    (
        re.compile(
            r"\b(however|furthermore|additionally|basically|actually|simply)\b",
            re.IGNORECASE,
        ),
        "",
    ),
)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _fire_webhook(
    webhook_url: str,
    payload: dict,
) -> None:
    """Fire-and-forget POST to webhook_url. Errors are logged, not raised."""
    parsed = urlparse(webhook_url)
    safe_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json=payload, headers={"Content-Type": "application/json"})
            logger.info("Webhook %s → %d", safe_url, resp.status_code)
    except Exception as exc:
        logger.warning("Webhook delivery failed for %s: %s", safe_url, exc)


def _classify_error(exc: BaseException) -> tuple[str, str, int | None]:
    """Return (error_type, error_message, error_code) for a caught exception.

    error_type is one of:
      rate_limit_exceeded | authentication_error | connection_error |
      timeout_error | http_error | api_error | internal_error
    error_code is an HTTP status code when applicable, else None.
    """
    import anthropic as _anthropic  # local import to avoid circular dep at module level

    if isinstance(exc, _anthropic.RateLimitError):
        return ("rate_limit_exceeded", str(exc), 429)
    if isinstance(exc, _anthropic.AuthenticationError):
        return ("authentication_error", str(exc), 401)
    if isinstance(exc, _anthropic.APIConnectionError):
        return ("connection_error", str(exc), None)
    if isinstance(exc, _anthropic.APITimeoutError):
        return ("timeout_error", str(exc), None)
    if isinstance(exc, _anthropic.APIStatusError):
        return ("api_error", str(exc), exc.status_code)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return ("http_error", f"HTTP {status}: {exc.response.text[:200]}", status)
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return ("connection_error", str(exc), None)
    if isinstance(exc, (httpx.TimeoutException, TimeoutError)):
        return ("timeout_error", str(exc), None)
    return ("internal_error", str(exc), None)


async def _fire_error_webhook(
    workflow: "Workflow",
    exc: BaseException,
    task_exec: "TaskExecution | None",
    user_prompt: str,
) -> None:
    """Fire the error_webhook_url if configured, with a structured error payload."""
    if not workflow.error_webhook_url:
        return
    error_type, error_message, error_code = _classify_error(exc)
    elapsed: float | None = None
    if task_exec and task_exec.started_at and task_exec.finished_at:
        elapsed = (task_exec.finished_at - task_exec.started_at).total_seconds()
    payload: dict = {
        "task_id": str(task_exec.id) if task_exec else None,
        "workflow_id": str(workflow.id),
        "workflow_title": workflow.title,
        "prompt": user_prompt,
        "status": "failed",
        "error_type": error_type,
        "error_message": error_message,
        "error_code": error_code,
        "elapsed_seconds": elapsed,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await _fire_webhook(workflow.error_webhook_url, payload)


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


def _cavemanize_sentence(text: str) -> str:
    """Compress a prose sentence while preserving protected technical fragments."""
    if not text or not text.strip():
        return ""

    protected: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__CAVEMAN_{len(protected) - 1}__"

    working = _CAVEMAN_PROTECTED_RE.sub(_stash, text)
    for pattern, replacement in _CAVEMAN_REPLACEMENTS:
        working = pattern.sub(replacement, working)
    working = re.sub(r"\s+", " ", working).strip(" \t\r\n-:;,.")
    if not working:
        return text.strip()

    words = re.findall(r"__CAVEMAN_\d+__|[A-Za-z0-9_./:+-]+|[^\w\s]", working)
    compacted: list[str] = []
    for word in words:
        if word.startswith("__CAVEMAN_"):
            compacted.append(word)
            continue
        lowered = word.lower()
        if re.fullmatch(r"[A-Za-z]+", word) and lowered in _CAVEMAN_STOPWORDS:
            continue
        compacted.append(word)

    result = " ".join(compacted)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"\s+", " ", result).strip()
    for idx, token in enumerate(protected):
        result = result.replace(f"__CAVEMAN_{idx}__", token)
    return result or text.strip()


def _compress_caveman_context(text: str) -> str:
    """Compress XML-ish workflow context text without breaking tags."""
    if not text or not text.strip():
        return text

    parts = _CAVEMAN_TAG_SPLIT_RE.split(text)
    compressed_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("<") and part.endswith(">"):
            compressed_parts.append(part)
            continue

        sentences = [
            _cavemanize_sentence(html.unescape(sentence))
            for sentence in _CAVEMAN_SENTENCE_SPLIT_RE.split(part)
            if sentence.strip()
        ]
        rebuilt = "\n".join(html.escape(sentence, quote=False) for sentence in sentences)
        compressed_parts.append(rebuilt)

    compressed = "".join(compressed_parts)
    return compressed if len(compressed) < len(text) else text

def _clip_prompt_text(text: str, max_chars: int) -> str:
    """Trim prompt section text to a soft character budget."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def _estimate_text_tokens(text: str, model: str = "") -> int:
    """Estimate token count for a text string using the best available counter."""
    return count_tokens(text, model) if text else 0


def _clip_tool_description(text: str | None) -> str:
    """Keep repeated tool descriptions within a predictable budget."""
    if not text:
        return ""
    return _clip_prompt_text(str(text).strip(), settings.tool_definition_description_max_chars)


def _sanitize_json_schema(obj):
    """Strip schema noise that inflates repeated tool definitions."""
    if isinstance(obj, dict):
        sanitized: dict = {}
        for key, value in obj.items():
            if key == "properties" and isinstance(value, dict):
                property_map = {
                    prop_name: _sanitize_json_schema(prop_schema)
                    for prop_name, prop_schema in value.items()
                }
                sanitized["properties"] = {
                    prop_name: prop_schema
                    for prop_name, prop_schema in property_map.items()
                    if prop_schema not in ({}, [], "")
                }
                continue
            if key not in _ALLOWED_SCHEMA_KEYS:
                continue
            if key == "description":
                clipped = _clip_tool_description(str(value))
                if clipped:
                    sanitized[key] = clipped
                continue
            if key == "additionalProperties" and isinstance(value, bool):
                sanitized[key] = value
                continue
            cleaned = _sanitize_json_schema(value)
            if cleaned in ({}, [], ""):
                if key in {"properties", "required"}:
                    sanitized[key] = cleaned
                continue
            sanitized[key] = cleaned
        return sanitized
    if isinstance(obj, list):
        return [item for item in (_sanitize_json_schema(item) for item in obj) if item not in ({}, [], "")]
    return obj


def _estimate_tools_tokens(tools: list[dict]) -> int:
    """Estimate token count for serialized tool definitions."""
    if not tools:
        return 0
    return count_tokens(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))


def _estimate_request_tokens(
    messages: list[dict],
    tools: list[dict] | None = None,
    model: str = "",
) -> int:
    """Estimate token count for the full chat-completions request payload."""
    body: dict = {"messages": messages}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    return count_tokens(json.dumps(body, ensure_ascii=False, separators=(",", ":")), model)


def _truncate_tool_result(text: str, max_chars: int) -> str:
    """Bound tool result size before feeding it back into the next model turn."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    note = (
        f"\n\n[tool result truncated for context efficiency; original_length={len(text)} chars]"
    )
    content_budget = max_chars - len(note)
    if content_budget <= 0:
        return note.lstrip()
    return _clip_prompt_text(text, content_budget) + note


def _format_tool_result_for_context(text: str, *, prefer_tsv: bool = False) -> str:
    """Render tabular JSON tool results as plain TSV when it is smaller."""
    if not text or not prefer_tsv:
        return text
    try:
        payload = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return text

    candidate = _render_payload_as_tsv(payload)
    if not candidate or len(candidate) >= len(text):
        return text
    return candidate


def _render_payload_as_tsv(payload) -> str | None:
    """Convert a tabular JSON payload into TSV-oriented plain text."""
    if isinstance(payload, list):
        return _render_rows_as_tsv(payload)

    if not isinstance(payload, dict):
        return None

    preferred_keys = ("results", "rows", "items", "matches", "entries")
    table_key = next(
        (
            key
            for key in preferred_keys
            if key in payload and _looks_like_table(payload.get(key))
        ),
        None,
    )
    if table_key is None:
        return None

    table_text = _render_rows_as_tsv(payload.get(table_key))
    if not table_text:
        return None

    metadata_lines = []
    for key, value in payload.items():
        if key == table_key:
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            metadata_lines.append(f"{key}: {_stringify_table_value(value)}")

    if metadata_lines:
        return "\n".join([*metadata_lines, "", table_text])
    return table_text


def _looks_like_table(value) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(row, dict) for row in value)
    )


def _render_rows_as_tsv(rows) -> str | None:
    if not _looks_like_table(rows):
        return None

    headers: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            key_str = str(key)
            if key_str not in seen:
                headers.append(key_str)
                seen.add(key_str)
    if not headers:
        return None

    output = StringIO()
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_stringify_table_value(row.get(header)) for header in headers])
    return output.getvalue().rstrip("\n")


def _stringify_table_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


async def _log_store_memory_result(
    workflow: Workflow,
    task_exec: TaskExecution | None,
    tool_result: str,
) -> None:
    """Emit a dedicated log entry for store_memory outcomes across runtimes."""
    try:
        parsed = json.loads(tool_result)
    except (TypeError, json.JSONDecodeError):
        await _log(
            workflow,
            "memory_store_failed",
            "store_memory returned non-JSON output",
            task_exec,
            tool_output=str(tool_result)[:500],
        )
        return

    if not isinstance(parsed, dict):
        await _log(
            workflow,
            "memory_store_failed",
            "store_memory returned unexpected payload",
            task_exec,
            tool_output=json.dumps(parsed, default=str)[:500],
        )
        return

    if parsed.get("status") == "stored":
        key = parsed.get("key", "")
        scope = parsed.get("scope", "")
        await _log(
            workflow,
            "memory_stored",
            f"key={key} scope={scope}",
            task_exec,
            tool_output=json.dumps(parsed, ensure_ascii=False)[:500],
        )
        return

    error = parsed.get("error") or "store_memory failed"
    await _log(
        workflow,
        "memory_store_failed",
        str(error),
        task_exec,
        tool_output=json.dumps(parsed, ensure_ascii=False)[:500],
    )


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
) -> tuple[str, int]:
    """Assemble the system prompt from agent config + skills + knowledge + memories.

    Returns a tuple of (full_system_prompt, static_prefix_len) where static_prefix_len
    is the length of the static prefix (everything before knowledge/memory context).
    """
    system_prompt = agent.system_prompt

    # Skills — resolve by explicit ID first, then by tag (union, deduplicated)
    skill_tags = getattr(workflow, "skill_tags", []) or []
    if skill_ids or skill_tags:
        skill_sections: list[str] = []
        seen_ids: set[str] = set()
        total_skill_chars = 0

        def _add_skill_section(skill) -> bool:
            nonlocal total_skill_chars
            remaining_budget = settings.prompt_skills_char_budget - total_skill_chars
            if remaining_budget <= 0:
                return False
            section_prefix = f'<skill name="{skill.name}">\n'
            section_suffix = "\n</skill>"
            instruction_budget = remaining_budget - len(section_prefix) - len(section_suffix)
            if instruction_budget <= 0:
                return False
            section = (
                section_prefix
                + f'{_clip_prompt_text(skill.instructions, instruction_budget)}\n'
                + '</skill>'
            )
            if total_skill_chars + len(section) > settings.prompt_skills_char_budget:
                return False
            skill_sections.append(section)
            total_skill_chars += len(section) + 1
            return True

        for sid in skill_ids:
            skill = await Skill.get(sid)
            if skill:
                seen_ids.add(str(skill.id))
                if not _add_skill_section(skill):
                    break

        for tag in skill_tags:
            if total_skill_chars >= settings.prompt_skills_char_budget:
                break
            tag_skills = await Skill.find({"tags": tag}).to_list()
            for skill in tag_skills:
                sid = str(skill.id)
                if sid not in seen_ids:
                    seen_ids.add(sid)
                    if not _add_skill_section(skill):
                        break
        if skill_sections:
            system_prompt += "\n\n<skills>\n" + "\n".join(skill_sections) + "\n</skills>"

    if getattr(workflow, "caveman", False):
        target_format = (
            "JSON payload"
            if workflow.output_format == OutputFormat.JSON
            else "markdown"
        )
        system_prompt += (
            "\n\n<caveman_policy>"
            "\nUse caveman mode for final responses: terse, direct, technically exact."
            "\nDrop filler, pleasantries, and hedging. Fragments OK."
            "\nKeep code, commands, file paths, URLs, versions, and identifiers exact."
            "\nEven in caveman mode, still satisfy full user intent and the "
            f"workflow output obligation ({target_format})."
            "\nIf safety or irreversible-action clarity matters, be explicit first,"
            " then resume terse style."
            "\n</caveman_policy>"
        )

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

    # Auto-memory: instruct the agent to store learnings using store_memory tool
    if workflow.auto_memory:
        system_prompt += (
            "\n\n<auto_memory_policy>"
            "\nBefore completing your final response, reflect on this conversation and "
            "use the store_memory tool to save any key learnings, decisions, user "
            "preferences, or issues to avoid for future reference. Guidelines:"
            "\n- Only store genuinely useful, persistent information"
            "\n- Do NOT store trivial, obvious, or task-specific ephemeral details"
            "\n- Do NOT duplicate information already present in your existing memories"
            "\n- Use short snake_case keys (e.g. 'user_prefers_celsius', 'avoid_recursive_imports')"
            "\n- Keep values concise (1-2 sentences max)"
            "\n- Store at most 3 memories per task"
            "\n- Use scope 'agent' for agent-specific learnings"
            "\n- If there are no meaningful new learnings, do not call store_memory"
            "\n</auto_memory_policy>"
        )

    # Track the split: everything up to here is "static"; knowledge/memory are "dynamic"
    static_end = len(system_prompt)

    # Knowledge
    if knowledge_context:
        system_prompt += "\n\n" + knowledge_context

    # Memories
    if memory_context:
        system_prompt += "\n\n" + memory_context

    if len(system_prompt) > settings.prompt_context_char_budget:
        system_prompt = _clip_prompt_text(system_prompt, settings.prompt_context_char_budget)

    return system_prompt, static_end


def _build_anthropic_system_blocks(system_prompt: str, static_prefix_len: int) -> list[dict]:
    """Split system_prompt into Anthropic content blocks with cache_control on the static prefix.

    Anthropic requires >=1024 tokens (~4096 chars) for a cache breakpoint to be effective.
    If the static prefix is too short, return a single block without cache_control.
    """
    _ANTHROPIC_CACHE_MIN_CHARS = 4096  # ~1024 tokens, Anthropic's minimum cacheable size
    static_text = system_prompt[:static_prefix_len]
    dynamic_text = system_prompt[static_prefix_len:]

    if len(static_text) >= _ANTHROPIC_CACHE_MIN_CHARS:
        blocks: list[dict] = [
            {
                "type": "text",
                "text": static_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        if dynamic_text:
            blocks.append({"type": "text", "text": dynamic_text})
        return blocks
    else:
        # Prefix too short to benefit from caching — single block, no cache_control
        return [{"type": "text", "text": system_prompt}]


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

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _compute_retry_delay(attempt: int, response: httpx.Response | None = None) -> float:
    """Compute retry delay, honouring Retry-After header when available."""
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return _RETRY_BASE_DELAY * (2 ** attempt)


async def _http_post_with_retry(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body: dict,
    *,
    max_retries: int = _MAX_RETRIES,
) -> httpx.Response:
    """POST with exponential backoff for rate limits and transient errors."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.post(url, headers=headers, json=body)
            if response.status_code not in _RETRYABLE_STATUS_CODES or attempt == max_retries:
                response.raise_for_status()
                return response
            # Retryable status — compute delay
            delay = _compute_retry_delay(attempt, response)
            logger.warning(
                "Provider returned %d, retrying in %.1fs (attempt %d/%d)",
                response.status_code, delay, attempt + 1, max_retries,
            )
            await asyncio.sleep(delay)
        except httpx.HTTPStatusError:
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = _compute_retry_delay(attempt)
            logger.warning(
                "Provider connection error: %s, retrying in %.1fs (attempt %d/%d)",
                exc, delay, attempt + 1, max_retries,
            )
            await asyncio.sleep(delay)
    # Should not reach here, but satisfy type checker
    raise last_exc or RuntimeError("Retry logic exhausted")


async def _stream_chat_completion(
    client: httpx.AsyncClient,
    url: str,
    headers: dict,
    body: dict,
    workflow_id: str,
) -> dict:
    """Stream an OpenAI-compatible chat completion, publishing deltas via event_bus.

    Returns a synthetic response dict matching the non-streaming format so callers
    don't need separate handling.
    """
    body = {**body, "stream": True, "stream_options": {"include_usage": True}}

    # Retry wrapper for initial streaming connection
    last_exc: Exception | None = None
    raw_response: httpx.Response | None = None
    for attempt in range(_MAX_RETRIES + 1):
        try:
            req = client.build_request("POST", url, headers=headers, json=body)
            raw_response = await client.send(req, stream=True)
            if raw_response.status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES:
                delay = _compute_retry_delay(attempt, raw_response)
                await raw_response.aclose()
                logger.warning(
                    "Streaming: provider returned %d, retrying in %.1fs (attempt %d/%d)",
                    raw_response.status_code, delay, attempt + 1, _MAX_RETRIES,
                )
                await asyncio.sleep(delay)
                continue
            raw_response.raise_for_status()
            break
        except httpx.HTTPStatusError:
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_exc = exc
            if attempt == _MAX_RETRIES:
                raise
            delay = _compute_retry_delay(attempt)
            await asyncio.sleep(delay)

    if raw_response is None:
        raise last_exc or RuntimeError("Streaming retry exhausted")

    # Parse SSE stream
    content_parts: list[str] = []
    tool_calls_map: dict[int, dict] = {}  # index -> {id, type, function: {name, arguments}}
    finish_reason = ""
    usage_data: dict = {}

    try:
        async for line in raw_response.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].lstrip()
            if payload == "[DONE]":
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError:
                continue

            # Usage is in the final chunk (when stream_options.include_usage is set)
            if "usage" in chunk and chunk["usage"]:
                usage_data = chunk["usage"]

            choices = chunk.get("choices") or []
            if not choices:
                continue

            delta = choices[0].get("delta", {})
            fr = choices[0].get("finish_reason")
            if fr:
                finish_reason = fr

            # Content delta
            content_delta = delta.get("content")
            if content_delta:
                content_parts.append(content_delta)
                asyncio.create_task(event_bus.publish(
                    workflow_id, "message_delta", {"delta": content_delta},
                ))

            # Tool call deltas
            tc_deltas = delta.get("tool_calls") or []
            for tcd in tc_deltas:
                idx = tcd.get("index", 0)
                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {
                        "id": tcd.get("id", ""),
                        "type": tcd.get("type", "function"),
                        "function": {"name": "", "arguments": ""},
                    }
                existing = tool_calls_map[idx]
                if tcd.get("id"):
                    existing["id"] = tcd["id"]
                func_delta = tcd.get("function", {})
                if func_delta.get("name"):
                    existing["function"]["name"] += func_delta["name"]
                if func_delta.get("arguments"):
                    existing["function"]["arguments"] += func_delta["arguments"]
    finally:
        await raw_response.aclose()

    # Build synthetic non-streaming response
    message: dict = {}
    if content_parts:
        message["content"] = "".join(content_parts)
    if tool_calls_map:
        message["tool_calls"] = [tool_calls_map[i] for i in sorted(tool_calls_map)]
    message.setdefault("role", "assistant")

    return {
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": usage_data,
    }


def _build_provider_headers(provider: Provider, api_key: str) -> dict[str, str]:
    """Build HTTP headers for a provider request."""
    provider_type = provider.provider_type
    if provider_type == ProviderType.ANTHROPIC:
        return {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "prompt-caching-2024-07-31",
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


def _clear_old_tool_results(
    messages: list[dict], keep_recent: int
) -> tuple[list[dict], int]:
    """Replace content of older tool-result messages with a short placeholder.

    Keeps the *keep_recent* most recent tool-call / tool-result pairs intact.
    Returns the modified message list and the number of messages cleared.
    """
    # Identify tool-result message indices (oldest first)
    tool_indices = [
        i for i, m in enumerate(messages)
        if m.get("role") == "tool"
    ]
    # Keep the last keep_recent tool results; clear the rest
    to_clear = tool_indices[: max(0, len(tool_indices) - keep_recent)]
    if not to_clear:
        return messages, 0

    cleared_msgs = list(messages)
    for idx in to_clear:
        orig = cleared_msgs[idx]
        cleared_msgs[idx] = {
            **orig,
            "content": "[tool result cleared for context efficiency]",
        }
    return cleared_msgs, len(to_clear)


def _compact_messages(
    messages: list[dict],
    model: str = "",
    context_window: int = 128_000,
    force: bool = False,
) -> list[dict]:
    """Compact message history to fit within the context window.

    Two-pass strategy:
      1. **Tool-result clearing**: replace content of older tool messages with
         a short placeholder (preserves conversation structure).
      2. **Head/tail truncation**: if still too long, keep system + first user
         + recent turns and insert a compaction note.

    Only triggers when message count > 8 or *force* is True.
    """
    if not force and len(messages) <= 8:
        return messages

    # Pass 1 — tool-result clearing
    keep_recent_tool = settings.tool_result_clearing_keep_recent
    if settings.tool_result_clearing_enabled:
        messages, _cleared = _clear_old_tool_results(messages, keep_recent_tool)

    # Re-check length after clearing
    if not force and len(messages) <= 8:
        return messages

    keep_recent = settings.compaction_keep_recent_turns

    kept_head = [messages[0]]  # system prompt
    # Find the first user message
    first_user_idx = 1
    for i, m in enumerate(messages[1:], start=1):
        if m.get("role") == "user":
            first_user_idx = i
            break
    kept_head.append(messages[first_user_idx])

    # Keep the last N turns
    tail_start = max(len(kept_head), len(messages) - keep_recent)
    kept_tail = messages[tail_start:]

    dropped_count = len(messages) - len(kept_head) - len(kept_tail)
    if dropped_count <= 0:
        return messages

    compaction_note = {
        "role": "system",
        "content": (
            f"[Context compacted: {dropped_count} intermediate messages were removed "
            "to fit within the context window. The conversation continues below.]"
        ),
    }
    return kept_head + [compaction_note] + kept_tail


def _resolve_provider_url(provider: Provider, model: str = "") -> str:
    """Resolve the chat completions endpoint URL for a provider.

    For Azure OpenAI, builds the deployment-specific URL with api-version.
    For others, appends ``/chat/completions`` to the base URL.
    """
    raw_url = provider.base_url or PROVIDER_DEFAULT_BASE_URLS.get(provider.provider_type)
    if raw_url is None:
        raise ValueError(
            f"Provider '{provider.name}' has no base_url configured and none is available "
            f"for provider_type '{provider.provider_type}'."
        )
    base = raw_url.rstrip("/")
    if provider.provider_type == ProviderType.AZURE_OPENAI:
        # Support both Azure base_url formats:
        #   - https://resource.openai.azure.com
        #   - https://resource.openai.azure.com/openai/deployments/my-deploy
        azure_deployments_path = "/openai/deployments/"
        azure_resource_base = base
        existing_deployment = ""
        if azure_deployments_path in base:
            azure_resource_base, deployment_suffix = base.split(azure_deployments_path, 1)
            existing_deployment = deployment_suffix.strip("/").split("/", 1)[0]
            azure_resource_base = azure_resource_base.rstrip("/")

        deployment = provider.azure_deployment or model or existing_deployment
        if not deployment:
            raise ValueError(
                f"Azure OpenAI provider '{provider.name}' requires a deployment name. "
                "Set azure_deployment on the provider or use the workflow model field."
            )
        api_version = provider.azure_api_version
        return (
            f"{azure_resource_base}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={api_version}"
        )
    return base + "/chat/completions"


def _mcp_tool_to_openai(tool) -> dict:
    """Convert an MCP Tool object to OpenAI function-calling tool format."""
    schema = dict(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}
    defs = schema.get("$defs", {})
    if defs:
        schema = _resolve_refs(schema, defs)
    schema = _sanitize_json_schema(schema)
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": _clip_tool_description(tool.description),
            "parameters": schema,
        },
    }


async def _connect_mcp_and_list_tools(
    mcp_config: dict,
    allowed_tools_set: set[str] | None,
    exit_stack,
    *,
    formatter=None,
) -> tuple[list[dict], dict]:
    """Connect to MCP servers and list their tools.

    Returns ``(tools, tool_server_map)`` where ``tool_server_map``
    maps tool names to ``(session, server_name)`` tuples for later invocation.
    The *formatter* callable converts each MCP Tool object to the target API
    format (default: :func:`_mcp_tool_to_openai` for OpenAI-compat format).

    The caller-provided ``exit_stack`` (``AsyncExitStack``) manages the
    lifetime of all MCP connections so they stay open for tool invocations.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.sse import sse_client
    from mcp.client.stdio import stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    if formatter is None:
        formatter = _mcp_tool_to_openai

    tools: list[dict] = []
    tool_server_map: dict[str, tuple[ClientSession, str]] = {}

    for server_name, server_cfg in mcp_config.items():
        transport_type = server_cfg.get("type", "")
        configured_tools = server_cfg.get("tools") or ["*"]
        allow_all_tools = "*" in configured_tools
        configured_tool_names = set(configured_tools) if not allow_all_tools else set()

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
                if not allow_all_tools and tool.name not in configured_tool_names:
                    continue
                # Respect allowed_tools filter
                if allowed_tools_set is not None and tool.name not in allowed_tools_set:
                    continue
                tools.append(formatter(tool))
                tool_server_map[tool.name] = (session, server_name)
        except Exception as exc:
            logger.warning("Failed to connect MCP server '%s' for BYOK tools: %s", server_name, exc)

    return tools, tool_server_map


# ── Custom Python tool helpers ────────────────────────────────────────────────


async def _build_custom_tools_config(
    custom_tool_ids: list[str],
) -> tuple[list[dict], list[dict], dict[str, CustomTool]]:
    """Load enabled CustomTool documents and build tool definition lists.

    Returns:
        openai_tool_defs  — OpenAI function-calling format (for BYOK path)
        claude_tool_defs  — Claude Agent SDK custom format (for Claude path)
        tool_fn_map       — tool name → CustomTool (for execution routing)
    """
    from beanie import PydanticObjectId as _CtObjId

    openai_defs: list[dict] = []
    claude_defs: list[dict] = []
    fn_map: dict[str, CustomTool] = {}

    for tid in custom_tool_ids:
        try:
            tool = await CustomTool.get(_CtObjId(tid))
        except Exception:
            logger.warning("Skipping invalid custom_tool_id: %s", tid)
            continue
        _append_custom_tool_definition(tool, openai_defs, claude_defs, fn_map)

    return openai_defs, claude_defs, fn_map


def _append_custom_tool_definition(
    tool: CustomTool | None,
    openai_defs: list[dict],
    claude_defs: list[dict],
    fn_map: dict[str, CustomTool],
) -> bool:
    """Append a single enabled custom tool to the target definition lists."""
    if not tool or not tool.is_enabled or tool.name in fn_map:
        return False

    schema = tool.parameters_schema or {"type": "object", "properties": {}}

    openai_defs.append({
        "type": "function",
        "function": {
            "name": tool.name,
            "description": _clip_tool_description(tool.description),
            "parameters": _sanitize_json_schema(schema),
        },
    })
    allowed_keys = {"type", "properties", "required", "description", "additionalProperties"}
    claude_schema = {k: v for k, v in schema.items() if k in allowed_keys}
    claude_schema.setdefault("type", "object")
    claude_schema.setdefault("properties", {})
    claude_defs.append({
        "type": "custom",
        "name": tool.name,
        "description": _clip_tool_description(tool.description),
        "input_schema": claude_schema,
    })
    fn_map[tool.name] = tool
    return True


async def _load_builtin_repo_inspector_tool() -> CustomTool | None:
    """Load the repo inspection tool that is auto-loaded from disk, if present."""
    try:
        tool = await CustomTool.find_one({"name": "repo_inspector"})
    except Exception as exc:
        logger.debug("Repo inspector lookup skipped: %s", exc)
        return None
    if not tool or not tool.is_enabled:
        return None
    return tool


def _build_custom_tool_runtime_env(repo_path: str | None = None) -> dict[str, str]:
    """Build per-workflow environment variables for custom tool execution."""
    runtime_env: dict[str, str] = {}
    if repo_path:
        runtime_env["TBD_AGENTS_REPO_ROOT"] = repo_path
    return runtime_env


async def _execute_custom_tool(
    tool_name: str,
    arguments: dict,
    fn_map: dict,
    runtime_env: dict[str, str] | None = None,
    credential_overrides: dict[str, str] | None = None,
) -> str:
    """Execute a custom Python tool from *fn_map* via the subprocess runner.

    If *credential_overrides* is provided, any env var declared in the tool's
    ``env_config`` can be redirected to a different token.  Only env vars that
    already exist in ``env_config`` may be overridden — unknown keys are silently
    ignored so workflows cannot inject arbitrary env vars.
    """
    tool = fn_map.get(tool_name)
    if not tool:
        return json.dumps({"error": f"Custom tool '{tool_name}' not found"})

    # Build effective env_config: start with the tool's own mapping, then apply
    # any workflow-level credential overrides (bare token names, not wrappers).
    effective_env_config = dict(getattr(tool, "env_config", {}) or {})
    if credential_overrides:
        for env_var, token_name in credential_overrides.items():
            if env_var in effective_env_config and token_name:
                effective_env_config[env_var] = "{{token:" + token_name + "}}"

    resolved_env = None
    if effective_env_config:
        from app.services import token_manager
        resolved_env = await token_manager.resolve_config(effective_env_config)

    merged_env = dict(resolved_env or {})
    if runtime_env:
        merged_env.update(runtime_env)

    return await custom_tool_runner.run_tool(
        tool.source_code, tool.name, arguments, env=merged_env or None
    )


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

# Anthropic messages API format for store_memory (no "type": "custom" wrapper)
STORE_MEMORY_TOOL_ANTHROPIC = {
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


_ALLOWED_SCHEMA_KEYS = {
    "type",
    "properties",
    "required",
    "description",
    "additionalProperties",
    "enum",
    "items",
    "oneOf",
    "anyOf",
    "allOf",
    "format",
    "minimum",
    "maximum",
    "minItems",
    "maxItems",
    "pattern",
    "nullable",
}


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
    schema = _sanitize_json_schema(schema)
    # Keep only the keys the API accepts.
    schema = {k: v for k, v in schema.items() if k in _ALLOWED_SCHEMA_KEYS}
    return {
        "type": "custom",
        "name": tool.name,
        "description": _clip_tool_description(tool.description),
        "input_schema": schema,
    }


def _mcp_tool_to_anthropic(tool) -> dict:
    """Convert an MCP Tool object to Anthropic messages API tool format."""
    schema = dict(tool.inputSchema) if tool.inputSchema else {"type": "object", "properties": {}}
    schema.setdefault("type", "object")
    schema.setdefault("properties", {})
    defs = schema.get("$defs", {})
    if defs:
        schema = _resolve_refs(schema, defs)
    schema = _sanitize_json_schema(schema)
    schema = {k: v for k, v in schema.items() if k in _ALLOWED_SCHEMA_KEYS}
    return {
        "name": tool.name,
        "description": _clip_tool_description(tool.description),
        "input_schema": schema,
    }


def _extract_anthropic_text(content) -> str:
    """Extract joined text from Anthropic messages API response content blocks."""
    parts = []
    for block in content:
        if hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts)


def _anthropic_block_to_dict(block) -> dict:
    """Convert an Anthropic SDK content block to a plain serializable dict."""
    if hasattr(block, "type"):
        if block.type == "text":
            return {"type": "text", "text": block.text}
        if block.type == "tool_use":
            return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": "text", "text": str(block)}


def _anthropic_content_to_str(content) -> str:
    """Convert Anthropic message content (str or list of blocks) to plain text for compaction."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("type", "")
                if t == "text":
                    parts.append(item.get("text", ""))
                elif t == "tool_use":
                    parts.append(f"[Tool call: {item.get('name', '')}({json.dumps(item.get('input', {}))})]")
                elif t == "tool_result":
                    parts.append(f"[Tool result: {item.get('content', '')}]")
            elif hasattr(item, "type"):
                if item.type == "text":
                    parts.append(item.text)
                elif item.type == "tool_use":
                    parts.append(f"[Tool call: {item.name}]")
        return "\n".join(parts)
    return str(content)


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
        configured_tools = server_cfg.get("tools") or ["*"]
        allow_all_tools = "*" in configured_tools
        configured_tool_names = set(configured_tools) if not allow_all_tools else set()

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
                if not allow_all_tools and tool.name not in configured_tool_names:
                    continue
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


def _copilot_tool_uses_mcp_allowlist(tool_name: str) -> bool:
    """Return whether Copilot SDK hooks should re-check MCP allowlists.

    The Copilot SDK already enforces MCP tool restrictions from the per-server
    ``tools`` lists passed at session creation, so the hook layer should never
    apply a second global allowlist check.
    """
    return False

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
    static_prefix_len: int,
    provider: Provider,
    api_key: str,
    task_exec: TaskExecution | None,
    *,
    base_url: str | None = None,
    auth_type: str = "x-api-key",
    repo_path: str | None = None,
    mcp_config: dict | None = None,
    allowed_tools_set: set[str] | None = None,
    builtin_tools: list[str] | None = None,
) -> str | None:
    """Execute a prompt using the Claude Agent SDK (beta.agents/sessions).

    Creates an environment, agent, and session on Anthropic's infrastructure
    (or a compatible third-party gateway when *base_url* is provided), then
    streams events. The Agent SDK handles the full agentic loop
    (planning, tool invocation, response generation) server-side — analogous
    to how the Copilot SDK path works.

    When *base_url* is set and ``CLAUDE_SDK_THIRD_PARTY_PROVIDERS_ENABLED`` is
    ``True``, all SDK requests are routed through that URL, enabling use with
    Anthropic-compatible gateways such as LiteLLM.

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
        client = build_claude_client(api_key, base_url=base_url, auth_type=auth_type)

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

        # ── Custom Python tools (user-supplied, Claude format) ────────────────
        custom_python_tool_map_claude: dict[str, CustomTool] = {}
        custom_tool_runtime_env = _build_custom_tool_runtime_env(repo_path)
        try:
            _agent_for_claude = await Agent.get(workflow.agent_id)
            if _agent_for_claude and _agent_for_claude.custom_tool_ids:
                _, _ct_claude_defs, custom_python_tool_map_claude = await _build_custom_tools_config(
                    _agent_for_claude.custom_tool_ids
                )
                if _ct_claude_defs:
                    custom_tools.extend(_ct_claude_defs)
                    await _log(
                        workflow, "custom_tools_loaded",
                        f"{len(_ct_claude_defs)} custom Python tool(s): {[t['name'] for t in _ct_claude_defs]}",
                        task_exec,
                    )
        except Exception as _ct_exc:
            logger.debug("Custom tool lookup skipped: %s", _ct_exc)

        if repo_path:
            repo_tool = await _load_builtin_repo_inspector_tool()
            repo_tool_added = _append_custom_tool_definition(
                repo_tool,
                [],
                custom_tools,
                custom_python_tool_map_claude,
            )
            if repo_tool_added:
                await _log(
                    workflow,
                    "repo_tool_loaded",
                    "repo_inspector exposed for repository-aware file inspection",
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
        # NOTE: The Anthropic agents beta API (/v1/agents) requires `system`
        # to be a plain string.  The cache-block format (list[dict]) is only
        # accepted by the messages API and would cause a 400
        # "system: value must be a string" error here.
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

                    # Execute — built-in memory, custom Python, or local MCP session
                    if tool_name == "store_memory":
                        tool_result = await _handle_store_memory(
                            workflow.agent_id, tool_args
                        )
                    elif tool_name in custom_python_tool_map_claude:
                        tool_result = await _execute_custom_tool(
                            tool_name,
                            tool_args,
                            custom_python_tool_map_claude,
                            runtime_env=custom_tool_runtime_env,
                            credential_overrides=workflow.credential_overrides or None,
                        )
                    else:
                        tool_result = await _execute_mcp_tool(
                            tool_name, tool_args, tool_server_map,
                        )
                    tool_result_for_model = _format_tool_result_for_context(
                        tool_result,
                        prefer_tsv=workflow.tsv_tool_results,
                    )
                    await _log(
                        workflow, "tool_result", f"{tool_name} completed", task_exec,
                        tool_output=tool_result_for_model[:500],
                    )
                    if tool_name == "store_memory":
                        await _log_store_memory_result(workflow, task_exec, tool_result)

                    # Send result back to the Claude Agent SDK session
                    await client.beta.sessions.events.send(
                        session.id,
                        events=[{
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": tool_use_id,
                            "content": [{"type": "text", "text": tool_result_for_model}],
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

        # ── Output guardrail enforcement ─────────────────────────────────────
        if final_text:
            output_violations = await enforce_output_guardrails(workflow, final_text)
            if output_violations:
                await _log(
                    workflow,
                    "output_guardrail_violation",
                    "; ".join(output_violations),
                    task_exec,
                )
                await event_bus.publish(
                    str(workflow.id), "output_guardrail_violation",
                    {"violations": output_violations},
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

        # Fire webhook if configured
        if task_exec and workflow.webhook_url:
            await _fire_webhook(
                workflow.webhook_url,
                {
                    "task_id": str(task_exec.id),
                    "workflow_id": str(workflow.id),
                    "workflow_title": workflow.title,
                    "prompt": user_prompt,
                    "response": final_text,
                    "status": "completed",
                    "elapsed_seconds": (task_exec.finished_at - task_exec.started_at).total_seconds() if task_exec.started_at and task_exec.finished_at else None,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
    except Exception as exc:
        exc_str = str(exc)
        # Detect HTML response — indicates the base_url is wrong (e.g. pointing to
        # the OpenAI-compat /api/v1 path instead of /api, or a completely wrong URL).
        if exc_str.lstrip().startswith("<!") or "<html" in exc_str[:200].lower():
            user_msg = (
                "Claude Agent SDK error: the provider base_url returned an HTML page "
                "instead of a valid API response. "
                "For OpenRouter, set base_url to 'https://openrouter.ai/api' "
                "(not '/api/v1'). "
                "For LiteLLM, use your proxy root URL (e.g. 'http://localhost:4000'). "
                "The Anthropic Agent SDK beta endpoints "
                "(/v1/environments, /v1/agents, /v1/sessions) must be reachable at "
                "the configured base URL."
            )
            logger.error("Claude SDK agent task failed (bad base_url endpoint): %s", user_msg)
        else:
            user_msg = f"Claude SDK agent task failed: {exc_str[:500]}"
            logger.exception("Claude SDK agent task failed: %s", exc)
        await _log(workflow, "error", user_msg, task_exec)
        await _publish_status(workflow, "failed")
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
        await _fire_error_webhook(workflow, exc, task_exec, user_prompt)
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


async def _run_with_anthropic_messages(
    workflow: Workflow,
    user_prompt: str,
    system_prompt: str,
    provider: Provider,
    api_key: str,
    task_exec: TaskExecution | None,
    *,
    repo_path: str | None = None,
    mcp_config: dict | None = None,
    allowed_tools_set: set[str] | None = None,
    auth_type: str = "x-api-key",
) -> str | None:
    """Execute a prompt via an Anthropic-compatible gateway using the Anthropic messages API.

    Used when the agent's provider type is ``anthropic`` but a custom ``base_url`` is set
    (gateway mode — e.g. OpenRouter, LiteLLM).  Uses ``AsyncAnthropic(base_url=...)`` with
    ``messages.create`` and a client-side agentic loop, preserving Anthropic-native tool
    formats, extended thinking support, and API features.

    This path cannot use the Claude Agent SDK beta endpoints (``/v1/environments``,
    ``/v1/agents``) because those are Anthropic-exclusive server-side infrastructure — they
    do not exist on third-party gateways.

    Provider routing decision:
    - ``anthropic`` + no ``base_url``  →  ``_run_with_claude_sdk``  (Anthropic server-side SDK)
    - ``anthropic`` + ``base_url`` set →  this function  (client-side, any Anthropic-compat gateway)
    - all other types                  →  ``_run_with_custom_provider``  (OpenAI-compat format)
    """
    from contextlib import AsyncExitStack
    from urllib.parse import urlparse as _urlparse

    from app.services.claude_client import build_claude_client

    model = workflow.model
    max_turns = workflow.max_turns
    task_start_time = datetime.now(UTC)
    agent_tasks_active.inc()
    final_text: str | None = None
    tool_call_count = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0
    total_cost = 0.0

    mcp_exit_stack = AsyncExitStack()
    await mcp_exit_stack.__aenter__()

    try:
        _parsed = _urlparse(provider.base_url or "")
        gateway_display = f"{_parsed.scheme}://{_parsed.netloc}"
        await _log(
            workflow,
            "provider_gateway",
            f"Anthropic provider '{provider.name}' using gateway mode: {gateway_display} "
            f"(model={model}, auth_type={auth_type}). Using Anthropic messages API with client-side loop.",
            task_exec,
        )

        client = build_claude_client(api_key, base_url=provider.base_url, auth_type=auth_type)

        # ── Discover MCP tools in Anthropic format ────────────────────────────
        anthropic_tools: list[dict] = []
        tool_server_map: dict = {}

        if mcp_config:
            anthropic_tools, tool_server_map = await _connect_mcp_and_list_tools(
                mcp_config, allowed_tools_set, mcp_exit_stack,
                formatter=_mcp_tool_to_anthropic,
            )
            if anthropic_tools:
                tools_chars = len(json.dumps(anthropic_tools, ensure_ascii=False, separators=(",", ":")))
                tools_tokens = _estimate_tools_tokens(anthropic_tools)
                await _log(
                    workflow,
                    "tools_discovered",
                    f"{len(anthropic_tools)} tool(s) available (~{tools_tokens} tokens, {tools_chars} chars): "
                    f"{[t['name'] for t in anthropic_tools][:12]}",
                    task_exec,
                )

        # ── Custom Python tools ───────────────────────────────────────────────
        custom_python_tool_map: dict[str, CustomTool] = {}
        custom_tool_runtime_env = _build_custom_tool_runtime_env(repo_path)
        try:
            _agent_for_custom = await Agent.get(workflow.agent_id)
            if _agent_for_custom and _agent_for_custom.custom_tool_ids:
                _, _ct_claude_defs, custom_python_tool_map = await _build_custom_tools_config(
                    _agent_for_custom.custom_tool_ids
                )
                # Convert Claude SDK custom format to Anthropic messages format (drop "type": "custom")
                _ct_anthropic_defs = [{k: v for k, v in t.items() if k != "type"} for t in _ct_claude_defs]
                if _ct_anthropic_defs:
                    anthropic_tools.extend(_ct_anthropic_defs)
                    await _log(
                        workflow, "custom_tools_loaded",
                        f"{len(_ct_anthropic_defs)} custom Python tool(s): {[t['name'] for t in _ct_anthropic_defs]}",
                        task_exec,
                    )
        except Exception as _ct_exc:
            logger.debug("Custom tool lookup skipped: %s", _ct_exc)

        if repo_path:
            repo_tool = await _load_builtin_repo_inspector_tool()
            _repo_openai_defs: list[dict] = []
            _repo_claude_defs: list[dict] = []
            repo_tool_added = _append_custom_tool_definition(
                repo_tool, _repo_openai_defs, _repo_claude_defs, custom_python_tool_map,
            )
            if repo_tool_added:
                _repo_anthropic_defs = [{k: v for k, v in t.items() if k != "type"} for t in _repo_claude_defs]
                anthropic_tools.extend(_repo_anthropic_defs)
                await _log(workflow, "repo_tool_loaded",
                           "repo_inspector exposed for repository-aware file inspection", task_exec)

        anthropic_tools.append(STORE_MEMORY_TOOL_ANTHROPIC)

        await _log(
            workflow,
            "model_call",
            f"Sending prompt to {model} via Anthropic gateway '{provider.name}' ({gateway_display})"
            f" (tools: {len(anthropic_tools)})",
            task_exec,
        )

        # Context compaction thresholds
        _raw_cw = getattr(workflow, "context_window", None)
        try:
            context_window = int(_raw_cw) if _raw_cw is not None else 128_000
        except (TypeError, ValueError):
            context_window = 128_000
        compaction_threshold = settings.compaction_token_threshold_pct

        # Anthropic format: system is a top-level param, not a message
        messages: list[dict] = [{"role": "user", "content": user_prompt}]

        # ── Agentic loop ──────────────────────────────────────────────────────
        iteration = 0
        while True:
            iteration += 1
            # Estimate tokens (include system in estimate for accuracy)
            _sys_msg = [{"role": "system", "content": system_prompt}]
            _flat_msgs = _sys_msg + [
                {"role": m["role"], "content": _anthropic_content_to_str(m["content"])}
                for m in messages
            ]
            current_prompt_tokens = _estimate_request_tokens(_flat_msgs, anthropic_tools, model)

            if iteration == 1 or current_prompt_tokens > context_window * compaction_threshold:
                await _log(
                    workflow,
                    "request_context",
                    f"Turn {iteration}: messages={len(messages)}, tools={len(anthropic_tools)}, "
                    f"estimated_request_tokens={current_prompt_tokens}",
                    task_exec,
                )

            if (
                settings.compaction_enabled
                and current_prompt_tokens > context_window * compaction_threshold
                and len(messages) > 4
            ):
                await _log(
                    workflow, "compaction_start",
                    f"Compacting context (request≈{current_prompt_tokens} tokens, "
                    f"messages={len(messages)}, tools={len(anthropic_tools)})",
                    task_exec,
                )
                _msgs_before = len(messages)
                # Flatten to OpenAI-compat format for compaction, then restore
                _compact_input = _sys_msg + [
                    {"role": m["role"], "content": _anthropic_content_to_str(m["content"])}
                    for m in messages
                ]
                _compact_output = _compact_messages(_compact_input, model=model, context_window=context_window)
                # Extract compaction note (injected as role=system by _compact_messages) before
                # filtering system messages, then append it to the top-level system prompt so
                # the model can see the context window note.
                _compaction_note = next(
                    (m["content"] for m in _compact_output
                     if m.get("role") == "system" and "[Context compacted:" in m.get("content", "")),
                    None,
                )
                messages = [{"role": m["role"], "content": m["content"]} for m in _compact_output if m["role"] != "system"]
                if _compaction_note:
                    system_prompt = system_prompt + "\n\n" + _compaction_note
                _dropped = _msgs_before - len(messages)  # based on actual pre/post message counts
                context_compactions_total.labels(model=model).inc()
                context_compaction_messages_dropped.labels(model=model).observe(max(0, _dropped))
                await _log(
                    workflow, "compaction_complete",
                    f"Compacted to {len(messages)} messages", task_exec,
                )

            # ── API call ─────────────────────────────────────────────────────
            try:
                response = await client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=messages,
                    tools=anthropic_tools if anthropic_tools else [],
                    max_tokens=settings.anthropic_gateway_max_tokens,
                )
            except Exception as exc:
                await _log(workflow, "error", f"Anthropic gateway API error: {exc}", task_exec)
                raise

            usage_data = getattr(response, "usage", None)
            if usage_data:
                total_input_tokens += getattr(usage_data, "input_tokens", 0) or 0
                total_output_tokens += getattr(usage_data, "output_tokens", 0) or 0
                total_cache_read_tokens += getattr(usage_data, "cache_read_input_tokens", 0) or 0
                total_cache_write_tokens += getattr(usage_data, "cache_creation_input_tokens", 0) or 0

            # ── Handle tool use ───────────────────────────────────────────────
            tool_use_blocks = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
            if tool_use_blocks and response.stop_reason in ("tool_use", None):
                # Append full assistant turn
                messages.append({
                    "role": "assistant",
                    "content": [_anthropic_block_to_dict(b) for b in response.content],
                })

                tool_results: list[dict] = []
                for block in tool_use_blocks:
                    tool_name = block.name
                    tool_args = block.input if isinstance(block.input, dict) else {}
                    tool_call_count += 1

                    if tool_name == "manage_todo_list":
                        progress = _parse_todo_list(tool_args)
                        if progress:
                            await _update_progress(workflow, task_exec, progress)

                    await _log(
                        workflow, "tool_call", tool_name, task_exec,
                        tool_input=json.dumps(tool_args)[:500],
                    )

                    try:
                        if tool_name == "store_memory":
                            tool_result = await _handle_store_memory(workflow.agent_id, tool_args)
                        elif tool_name in custom_python_tool_map:
                            tool_result = await _execute_custom_tool(
                                tool_name, tool_args, custom_python_tool_map,
                                runtime_env=custom_tool_runtime_env,
                                credential_overrides=workflow.credential_overrides or None,
                            )
                        else:
                            tool_result = await _execute_mcp_tool(tool_name, tool_args, tool_server_map)
                    except Exception as tool_exc:
                        tool_result = f"Tool execution error: {tool_exc}"
                        logger.warning("Tool '%s' raised an exception: %s", tool_name, tool_exc)

                    tool_result_for_model = _format_tool_result_for_context(
                        tool_result, prefer_tsv=workflow.tsv_tool_results,
                    )
                    await _log(
                        workflow, "tool_result", f"{tool_name} completed", task_exec,
                        tool_output=tool_result_for_model[:500],
                    )
                    if tool_name == "store_memory":
                        await _log_store_memory_result(workflow, task_exec, tool_result)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": _truncate_tool_result(
                            tool_result_for_model, settings.tool_result_context_max_chars,
                        ),
                    })

                # All tool results go back as a single user turn
                messages.append({"role": "user", "content": tool_results})

                # Check max turns
                if tool_call_count >= max_turns:
                    await _log(
                        workflow, "max_turns",
                        f"Reached max tool turns ({max_turns}), requesting final answer",
                        task_exec,
                    )
                    messages.append({
                        "role": "user",
                        "content": "You have reached the maximum number of tool calls. "
                        "Please provide your final answer based on the information gathered so far.",
                    })
                    final_response = await client.messages.create(
                        model=model, system=system_prompt, messages=messages,
                        max_tokens=8192,
                    )
                    fu = getattr(final_response, "usage", None)
                    if fu:
                        total_input_tokens += getattr(fu, "input_tokens", 0) or 0
                        total_output_tokens += getattr(fu, "output_tokens", 0) or 0
                    final_text = _extract_anthropic_text(final_response.content)
                    break

                continue

            # ── Final text response ───────────────────────────────────────────
            final_text = _extract_anthropic_text(response.content)
            break

        # ── Record usage & finalize ───────────────────────────────────────────
        usage = UsageStats(
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cache_read_tokens=total_cache_read_tokens,
            total_cache_write_tokens=total_cache_write_tokens,
            total_cost=total_cost,
        )
        workflow.usage = usage
        if total_input_tokens:
            tokens_total.labels(direction="input", model=model).inc(total_input_tokens)
        if total_output_tokens:
            tokens_total.labels(direction="output", model=model).inc(total_output_tokens)
        if total_cache_read_tokens:
            tokens_total.labels(direction="cache_read", model=model).inc(total_cache_read_tokens)
        if total_cache_write_tokens:
            tokens_total.labels(direction="cache_write", model=model).inc(total_cache_write_tokens)
        if tool_call_count:
            tool_calls_total.labels(tool_name="anthropic_gateway_aggregate").inc(tool_call_count)
        tool_calls_per_task.labels(model=model).observe(tool_call_count)

        workflow.messages.append(Message(role="assistant", content=final_text or ""))

        if final_text:
            output_violations = await enforce_output_guardrails(workflow, final_text)
            if output_violations:
                await _log(
                    workflow, "output_guardrail_violation",
                    "; ".join(output_violations), task_exec,
                )
                await event_bus.publish(
                    str(workflow.id), "output_guardrail_violation",
                    {"violations": output_violations},
                )

        if final_text and workflow.output_format == OutputFormat.JSON:
            final_text = json.dumps({"response": final_text})

        await _log(workflow, "model_response", (final_text or "")[:200], task_exec)

        if tool_call_count >= max_turns:
            task_final_status = TaskStatus.MAX_TURNS_REACHED
        else:
            task_final_status = TaskStatus.COMPLETED

        await _log(
            workflow, "completed",
            f"Final status: {task_final_status} (tool_calls: {tool_call_count})",
            task_exec,
        )
        await _publish_status(workflow, task_final_status)

        task_duration = (datetime.now(UTC) - task_start_time).total_seconds()
        agent_task_duration_seconds.labels(model=model, status=task_final_status).observe(task_duration)
        if usage.total_cost > 0:
            cost_per_task_dollars.labels(model=model).observe(usage.total_cost)

        if task_exec:
            task_exec.status = task_final_status
            task_exec.finished_at = datetime.now(UTC)
            task_exec.tool_calls = tool_call_count
            task_exec.response = final_text
            task_exec.usage = usage
            task_exec.messages = [m for m in workflow.messages if m.role == "assistant"][-20:]
            await task_exec.save()

        await workflow.save()

        if task_exec and workflow.webhook_url and task_final_status == TaskStatus.COMPLETED:
            await _fire_webhook(
                workflow.webhook_url,
                {
                    "task_id": str(task_exec.id),
                    "workflow_id": str(workflow.id),
                    "workflow_title": workflow.title,
                    "prompt": user_prompt,
                    "response": final_text,
                    "status": "completed",
                    "elapsed_seconds": (
                        (task_exec.finished_at - task_exec.started_at).total_seconds()
                        if task_exec.started_at and task_exec.finished_at else None
                    ),
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

    except Exception as exc:
        await _log(workflow, "error", f"Anthropic gateway error: {exc}", task_exec)
        await _publish_status(workflow, "failed")
        logger.exception("Anthropic messages path failed for workflow %s", workflow.id)
        if task_exec:
            task_exec.status = TaskStatus.FAILED
            task_exec.finished_at = datetime.now(UTC)
            await task_exec.save()
        final_text = None
        await workflow.save()
        await _fire_error_webhook(workflow, exc, task_exec, user_prompt)
    finally:
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


async def _run_with_custom_provider(
    workflow: Workflow,
    user_prompt: str,
    system_prompt: str,
    provider: Provider,
    api_key: str,
    task_exec: TaskExecution | None,
    *,
    repo_path: str | None = None,
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
    total_cache_read_tokens = 0
    total_cache_write_tokens = 0
    total_cost = 0.0

    try:
        from contextlib import AsyncExitStack
        mcp_exit_stack = AsyncExitStack()
        await mcp_exit_stack.__aenter__()

        url = _resolve_provider_url(provider, model)
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
                tools_chars = len(json.dumps(openai_tools, ensure_ascii=False, separators=(",", ":")))
                tools_tokens = _estimate_tools_tokens(openai_tools)
                await _log(
                    workflow,
                    "tools_discovered",
                    f"{len(openai_tools)} tool(s) available (~{tools_tokens} tokens, {tools_chars} chars): "
                    f"{[t['function']['name'] for t in openai_tools][:12]}",
                    task_exec,
                )

        # ── Custom Python tools (user-supplied) ──────────────────────────────
        custom_python_tool_map: dict[str, CustomTool] = {}
        custom_tool_runtime_env = _build_custom_tool_runtime_env(repo_path)
        try:
            _agent_for_custom = await Agent.get(workflow.agent_id)
            if _agent_for_custom and _agent_for_custom.custom_tool_ids:
                _ct_openai, _, custom_python_tool_map = await _build_custom_tools_config(
                    _agent_for_custom.custom_tool_ids
                )
                if _ct_openai:
                    openai_tools.extend(_ct_openai)
                    await _log(
                        workflow, "custom_tools_loaded",
                        f"{len(_ct_openai)} custom Python tool(s): {[t['function']['name'] for t in _ct_openai]}",
                        task_exec,
                    )
        except Exception as _ct_exc:
            logger.debug("Custom tool lookup skipped: %s", _ct_exc)

        if repo_path:
            repo_tool = await _load_builtin_repo_inspector_tool()
            repo_tool_openai_defs: list[dict] = []
            repo_tool_added = _append_custom_tool_definition(
                repo_tool,
                repo_tool_openai_defs,
                [],
                custom_python_tool_map,
            )
            if repo_tool_added:
                openai_tools.extend(repo_tool_openai_defs)
                await _log(
                    workflow,
                    "repo_tool_loaded",
                    "repo_inspector exposed for repository-aware file inspection",
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

        # Context compaction thresholds
        _raw_cw = getattr(workflow, "context_window", None)
        try:
            context_window = int(_raw_cw) if _raw_cw is not None else 128_000
        except (TypeError, ValueError):
            context_window = 128_000
        compaction_threshold = settings.compaction_token_threshold_pct

        # ── Agentic loop ────────────────────────────────────────────────────
        async with httpx.AsyncClient(timeout=settings.session_timeout) as http:
            iteration = 0
            while True:
                iteration += 1
                # ── Context compaction ───────────────────────────────────
                # If the current request context exceeds the compaction threshold,
                # prune older intermediate messages to free context space.
                current_prompt_tokens = _estimate_request_tokens(messages, openai_tools, model)
                if iteration == 1 or current_prompt_tokens > context_window * compaction_threshold:
                    await _log(
                        workflow,
                        "request_context",
                        f"Turn {iteration}: messages={len(messages)}, tools={len(openai_tools)}, "
                        f"estimated_request_tokens={current_prompt_tokens}, "
                        f"estimated_message_tokens={estimate_messages_tokens(messages, model)}, "
                        f"estimated_tool_tokens={_estimate_tools_tokens(openai_tools)}",
                        task_exec,
                    )
                if (
                    settings.compaction_enabled
                    and current_prompt_tokens > context_window * compaction_threshold
                    and len(messages) > 4
                ):
                    await _log(
                        workflow, "compaction_start",
                        f"Compacting context (request≈{current_prompt_tokens} tokens, "
                        f"messages={len(messages)}, tools={len(openai_tools)})",
                        task_exec,
                    )
                    _msgs_before = len(messages)
                    messages = _compact_messages(messages, model=model, context_window=context_window)
                    compacted_count = len(messages)
                    _dropped = _msgs_before - compacted_count + 1  # +1 for injected compaction note
                    context_compactions_total.labels(model=model).inc()
                    context_compaction_messages_dropped.labels(model=model).observe(max(0, _dropped))
                    await _log(
                        workflow, "compaction_complete",
                        f"Compacted to {compacted_count} messages "
                        f"(request≈{_estimate_request_tokens(messages, openai_tools, model)} tokens)",
                        task_exec,
                    )

                body: dict = {"model": model, "messages": messages}
                if openai_tools:
                    body["tools"] = openai_tools
                    body["tool_choice"] = "auto"

                try:
                    response = await _stream_chat_completion(
                        http, url, headers, body, str(workflow.id),
                    )
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        # Rate-limited — respect Retry-After header if present
                        retry_after = exc.response.headers.get("retry-after", "5")
                        try:
                            wait_secs = float(retry_after)
                        except ValueError:
                            wait_secs = 5.0
                        wait_secs = min(wait_secs, 60.0)
                        await _log(
                            workflow, "rate_limited",
                            f"Provider rate-limited; retrying after {wait_secs:.0f}s",
                            task_exec,
                        )
                        await asyncio.sleep(wait_secs)
                        continue
                    raise

                data = response

                # Track token usage (OpenAI, Azure OpenAI, and compatible APIs)
                usage_data = data.get("usage", {})
                total_input_tokens += int(usage_data.get("prompt_tokens", 0))
                total_output_tokens += int(usage_data.get("completion_tokens", 0))
                # Cache tokens (OpenAI prompt_tokens_details / completion_tokens_details)
                prompt_details = usage_data.get("prompt_tokens_details", {})
                total_cache_read_tokens += int(prompt_details.get("cached_tokens", 0))
                # Cost (returned by some providers)
                cost_val = usage_data.get("cost")
                if cost_val is not None:
                    total_cost += float(cost_val)

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

                        # Parse TODO progress from manage_todo_list calls
                        if tool_name == "manage_todo_list":
                            progress = _parse_todo_list(tool_args)
                            if progress:
                                await _update_progress(workflow, task_exec, progress)

                        await _log(
                            workflow, "tool_call", tool_name, task_exec,
                            tool_input=json.dumps(tool_args)[:500],
                        )

                        # Execute the tool — built-in memory, custom Python, or MCP
                        try:
                            if tool_name == "store_memory":
                                tool_result = await _handle_store_memory(
                                    workflow.agent_id, tool_args
                                )
                            elif tool_name in custom_python_tool_map:
                                tool_result = await _execute_custom_tool(
                                    tool_name,
                                    tool_args,
                                    custom_python_tool_map,
                                    runtime_env=custom_tool_runtime_env,
                                    credential_overrides=workflow.credential_overrides or None,
                                )
                            else:
                                tool_result = await _execute_mcp_tool(
                                    tool_name, tool_args, tool_server_map
                                )
                        except Exception as tool_exc:
                            tool_result = f"Tool execution error: {tool_exc}"
                            logger.warning(
                                "Tool '%s' raised an exception: %s", tool_name, tool_exc
                            )

                        tool_result_for_model = _format_tool_result_for_context(
                            tool_result,
                            prefer_tsv=workflow.tsv_tool_results,
                        )

                        await _log(
                            workflow, "tool_result", f"{tool_name} completed", task_exec,
                            tool_output=tool_result_for_model[:500],
                        )
                        if tool_name == "store_memory":
                            await _log_store_memory_result(workflow, task_exec, tool_result)

                        # Append tool result to conversation
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "content": _truncate_tool_result(
                                tool_result_for_model,
                                settings.tool_result_context_max_chars,
                            ),
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
                        final_data = await _stream_chat_completion(
                            http, url, headers, final_body, str(workflow.id),
                        )
                        fu = final_data.get("usage", {})
                        total_input_tokens += int(fu.get("prompt_tokens", 0))
                        total_output_tokens += int(fu.get("completion_tokens", 0))
                        fu_details = fu.get("prompt_tokens_details", {})
                        total_cache_read_tokens += int(fu_details.get("cached_tokens", 0))
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
            total_cache_read_tokens=total_cache_read_tokens,
            total_cache_write_tokens=total_cache_write_tokens,
            total_cost=total_cost,
        )
        workflow.usage = usage
        if total_input_tokens:
            tokens_total.labels(direction="input", model=model).inc(total_input_tokens)
        if total_output_tokens:
            tokens_total.labels(direction="output", model=model).inc(total_output_tokens)
        if total_cache_read_tokens:
            tokens_total.labels(direction="cache_read", model=model).inc(total_cache_read_tokens)
        if total_cache_write_tokens:
            tokens_total.labels(direction="cache_write", model=model).inc(total_cache_write_tokens)
        if total_cost > 0:
            cost_dollars_total.labels(model=model).inc(total_cost)
        if tool_call_count:
            tool_calls_total.labels(tool_name="byok_aggregate").inc(tool_call_count)
        tool_calls_per_task.labels(model=model).observe(tool_call_count)

        workflow.messages.append(Message(role="assistant", content=final_text or ""))

        # ── Output guardrail enforcement ─────────────────────────────────────
        if final_text:
            output_violations = await enforce_output_guardrails(workflow, final_text)
            if output_violations:
                await _log(
                    workflow,
                    "output_guardrail_violation",
                    "; ".join(output_violations),
                    task_exec,
                )
                await event_bus.publish(
                    str(workflow.id), "output_guardrail_violation",
                    {"violations": output_violations},
                )

        # Format output
        if final_text and workflow.output_format == OutputFormat.JSON:
            final_text = json.dumps({"response": final_text})

        await _log(workflow, "model_response", (final_text or "")[:200], task_exec)

        # Determine terminal status
        if tool_call_count >= max_turns:
            task_final_status = TaskStatus.MAX_TURNS_REACHED
        else:
            task_final_status = TaskStatus.COMPLETED

        await _log(
            workflow, "completed",
            f"Final status: {task_final_status} (tool_calls: {tool_call_count})",
            task_exec,
        )
        await _publish_status(workflow, task_final_status)

        task_duration = (datetime.now(UTC) - task_start_time).total_seconds()
        agent_task_duration_seconds.labels(
            model=model, status=task_final_status
        ).observe(task_duration)
        if usage.total_cost > 0:
            cost_per_task_dollars.labels(model=model).observe(usage.total_cost)

        if task_exec:
            task_exec.status = task_final_status
            task_exec.finished_at = datetime.now(UTC)
            task_exec.tool_calls = tool_call_count
            task_exec.response = final_text
            task_exec.usage = usage
            task_exec.messages = [m for m in workflow.messages if m.role == "assistant"][-20:]
            await task_exec.save()

        await workflow.save()

        # Fire webhook if configured and task completed successfully
        if task_exec and workflow.webhook_url and task_final_status == TaskStatus.COMPLETED:
            await _fire_webhook(
                workflow.webhook_url,
                {
                    "task_id": str(task_exec.id),
                    "workflow_id": str(workflow.id),
                    "workflow_title": workflow.title,
                    "prompt": user_prompt,
                    "response": final_text,
                    "status": "completed",
                    "elapsed_seconds": (task_exec.finished_at - task_exec.started_at).total_seconds() if task_exec.started_at and task_exec.finished_at else None,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )

    except httpx.HTTPStatusError as exc:
        # Streaming responses need an explicit read() before .text is accessible.
        try:
            await exc.response.aread()
        except Exception:
            pass
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
        await _fire_error_webhook(workflow, exc, task_exec, user_prompt)
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
        await _fire_error_webhook(workflow, exc, task_exec, user_prompt)
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
    github_token: str | None,
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

    # Build allowed-tools set for filtering in BYOK/MCP discovery paths.
    # The Copilot SDK path must not reuse this blindly inside the pre-tool hook,
    # because SDK built-ins like `view` / `glob` are not MCP tools.
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
            knowledge_sources_list,
            agent.knowledge_tags,
            max_chars=settings.prompt_knowledge_char_budget,
            item_limit=settings.prompt_context_max_items,
            query=user_prompt,
        )
        if knowledge_context:
            await _log(
                workflow,
                "knowledge_loaded",
                f"{len(knowledge_sources_list)} knowledge source(s) resolved "
                f"({len(knowledge_context)} chars, ~{_estimate_text_tokens(knowledge_context)} tokens)",
                task_exec,
            )
            if workflow.caveman:
                compressed = _compress_caveman_context(knowledge_context)
                if compressed != knowledge_context:
                    await _log(
                        workflow,
                        "caveman_context",
                        f"Compressed knowledge context {len(knowledge_context)}→{len(compressed)} chars",
                        task_exec,
                    )
                    knowledge_context = compressed

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
                limit=settings.prompt_context_max_items,
                max_chars=settings.prompt_memory_char_budget,
                query=user_prompt,
            )
            if memory_context:
                await _log(
                    workflow,
                    "memories_loaded",
                    f"Agent memories injected into context ({len(memory_context)} chars, "
                    f"~{_estimate_text_tokens(memory_context)} tokens)",
                    task_exec,
                )
                if workflow.caveman:
                    compressed = _compress_caveman_context(memory_context)
                    if compressed != memory_context:
                        await _log(
                            workflow,
                            "caveman_context",
                            f"Compressed memory context {len(memory_context)}→{len(compressed)} chars",
                            task_exec,
                        )
                        memory_context = compressed
        except Exception as exc:
            logger.warning("Failed to load memories for agent %s: %s", agent.id, exc)

    system_prompt, _static_prefix_len = await _build_system_prompt(
        agent, workflow.skill_ids, workflow, knowledge_context, memory_context
    )
    assembled_system_chars = len(system_prompt)

    # Sync repository if configured
    repo_path = await _sync_repo(workflow)
    repo_context = ""
    if repo_path:
        repo_sync_total.labels(status="success").inc()
        await _log(workflow, "repo_synced", f"Repository synced to {repo_path}", task_exec)
        repo_context = (
            f"\n\n<repository>\n"
            f"A git repository has been cloned and is available at: {repo_path}\n"
            f"URL: {workflow.repo_url}\n"
            f"Branch: {workflow.repo_branch or 'main'}\n"
            f"Use repository-aware tools to inspect this path when available. "
            f"If the repo_inspector tool is exposed, prefer it for listing, searching, and reading files instead of attempting shell access.\n"
            f"</repository>"
        )
        system_prompt += repo_context
    elif workflow.repo_url:
        repo_sync_total.labels(status="failure").inc()
        await _log(workflow, "repo_sync_failed", f"Failed to sync {workflow.repo_url}", task_exec)

    await _log(
        workflow,
        "context_budget",
        "Prompt context assembled "
        f"(base_system={len(agent.system_prompt)} chars, assembled_system={assembled_system_chars} chars, "
        f"knowledge={len(knowledge_context)} chars, memory={len(memory_context)} chars, "
        f"repo={len(repo_context)} chars, total={len(system_prompt)} chars, "
        f"~{_estimate_text_tokens(system_prompt, workflow.model)} tokens)",
        task_exec,
    )

    # ── Route to custom provider if set ──────────────────────────────────────
    if custom_provider and custom_provider_key:
        if custom_provider.provider_type == ProviderType.ANTHROPIC:
            if not custom_provider.base_url:
                # Direct Anthropic API — use the Claude Agent SDK (server-side agentic loop)
                return await _run_with_claude_sdk(
                    workflow,
                    user_prompt,
                    system_prompt,
                    _static_prefix_len,
                    custom_provider,
                    custom_provider_key,
                    task_exec,
                    auth_type=custom_provider.auth_type,
                    repo_path=repo_path,
                    mcp_config=mcp_config,
                    allowed_tools_set=allowed_tools_set,
                    builtin_tools=agent.builtin_tools or None,
                )
            # Gateway mode (base_url set, e.g. OpenRouter, LiteLLM) — use Anthropic
            # messages API with client-side agentic loop.  The Claude Agent SDK beta
            # endpoints (/v1/environments, /v1/agents) only exist on api.anthropic.com
            # and cannot be routed through third-party gateways.
            return await _run_with_anthropic_messages(
                workflow,
                user_prompt,
                system_prompt,
                custom_provider,
                custom_provider_key,
                task_exec,
                repo_path=repo_path,
                mcp_config=mcp_config,
                allowed_tools_set=allowed_tools_set,
                auth_type=custom_provider.auth_type,
            )
        return await _run_with_custom_provider(
            workflow,
            user_prompt,
            system_prompt,
            custom_provider,
            custom_provider_key,
            task_exec,
            repo_path=repo_path,
            mcp_config=mcp_config,
            allowed_tools_set=allowed_tools_set,
        )

    # ── Inject memory MCP server for Copilot SDK path ──────────────────────
    # The Copilot SDK only supports MCP-based tools (no custom tool defs).
    # Expose store_memory via a lightweight stdio MCP server subprocess so the
    # model can store memories when bypass_memory is off.
    if not getattr(workflow, "bypass_memory", False):
        mcp_config["__memory__"] = {
            "type": "stdio",
            "command": sys.executable,
            "args": ["-m", "app.core.memory_mcp_server"],
            "env": {
                **os.environ,
                "AGENT_ID": str(agent.id),
                "API_BASE_URL": settings.api_base_url,
                "API_TOKEN": github_token,
            },
            "tools": ["*"],
        }

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
        """Log tool invocation; deny only if max turns are exceeded.

        MCP tool restrictions are already enforced by the per-server ``tools``
        lists passed into the Copilot SDK session config. Re-checking them here
        with a flattened global allowlist causes false denials when runtime tool
        names or server-local catalogs do not line up exactly with the stored
        DB allowlists.
        """
        nonlocal tool_call_count
        tool_name = input_data.get("toolName", "unknown")
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
                        if str(tool_name) == "store_memory" and tool_output_str is not None:
                            asyncio.create_task(
                                _log_store_memory_result(workflow, task_exec, tool_output_str)
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
                # Infinite-session workflows are long-running investigations; give
                # them 24 h per prompt instead of the global SESSION_TIMEOUT.
                _prompt_timeout = 86400 if workflow.infinite_session else settings.session_timeout
                try:
                    deadline = asyncio.get_event_loop().time() + _prompt_timeout
                    while not done.is_set():
                        remaining = deadline - asyncio.get_event_loop().time()
                        if remaining <= 0:
                            raise TimeoutError()
                        try:
                            await asyncio.wait_for(done.wait(), timeout=min(2.0, remaining))
                        except TimeoutError:
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
                except TimeoutError:
                    workflow.current_turn = tool_call_count
                    await _log(
                        workflow,
                        "error",
                        f"Session timed out after {_prompt_timeout}s",
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

                # ── Output guardrail enforcement ─────────────────────────────
                if final_text:
                    output_violations = await enforce_output_guardrails(workflow, final_text)
                    if output_violations:
                        await _log(
                            workflow,
                            "output_guardrail_violation",
                            "; ".join(output_violations),
                            task_exec,
                        )
                        await event_bus.publish(
                            str(workflow.id), "output_guardrail_violation",
                            {"violations": output_violations},
                        )

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

                # Fire webhook if configured and task completed successfully
                if task_exec and workflow.webhook_url and task_final_status == TaskStatus.COMPLETED:
                    await _fire_webhook(
                        workflow.webhook_url,
                        {
                            "task_id": str(task_exec.id),
                            "workflow_id": str(workflow.id),
                            "workflow_title": workflow.title,
                            "prompt": user_prompt,
                            "response": final_text,
                            "status": "completed",
                            "elapsed_seconds": (task_exec.finished_at - task_exec.started_at).total_seconds() if task_exec.started_at and task_exec.finished_at else None,
                            "timestamp": datetime.now(UTC).isoformat(),
                        },
                    )

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
        await _fire_error_webhook(workflow, e, task_exec, user_prompt)
    finally:
        agent_tasks_active.dec()
        agent_tasks_total.labels(
            status=task_exec.status if task_exec else "completed",
            model=workflow.model,
            reasoning_effort=reasoning_effort or "default",
        ).inc()

    return final_text
