"""In-process LLM chat handler.

Handles multi-turn conversational interactions with an agent directly from
the FastAPI process — no Celery dispatch, no tool execution.

The handler:
1. Loads conversation history from MongoDB (``ChatMessage`` collection).
2. Builds a chat-specific system prompt from the agent's base prompt plus the
   self-awareness context block.
3. Calls the LLM directly via httpx (OpenAI-compatible streaming API).
4. Yields SSE event dicts as tokens arrive.
5. Persists the user message and the final assistant message to MongoDB.
6. Yields a ``done`` event with token usage stats.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from beanie import PydanticObjectId

from app.config import settings
from app.models.agent import Agent
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.provider import PROVIDER_DEFAULT_BASE_URLS, Provider, ProviderType
from app.observability import chat_messages_total, chat_response_duration_seconds
from app.services import token_manager
from app.services.chat_context import build_chat_context

logger = logging.getLogger(__name__)

# Default GitHub Copilot chat completions endpoint (OpenAI-compatible).
# This endpoint accepts GitHub tokens with the `copilot` scope — the same
# scope required by the Copilot SDK.  The GitHub Models endpoint
# (models.inference.ai.azure.com) requires a separate `models:read` scope
# and is NOT accepted by the standard `copilot`-scoped PAT used elsewhere.
_GITHUB_COPILOT_BASE_URL = "https://api.githubcopilot.com"

# Maximum messages to load from history (older messages are truncated)
_CONVERSATION_WINDOW = 50

# Per-response timeout in seconds
_CHAT_TIMEOUT = 120


# ── Event type dicts ─────────────────────────────────────────────────────────

ChatEvent = dict  # typed alias for clarity


def _session_event(session_id: str) -> ChatEvent:
    return {"type": "session", "session_id": session_id}


def _delta_event(content: str) -> ChatEvent:
    return {"type": "delta", "content": content}


def _done_event(usage: dict, message_id: str) -> ChatEvent:
    return {"type": "done", "usage": usage, "message_id": message_id}


def _error_event(message: str) -> ChatEvent:
    return {"type": "error", "message": message}


# ── Provider helpers ─────────────────────────────────────────────────────────


def _resolve_url(provider: Provider | None, model: str) -> str:
    """Resolve the chat completions URL for a provider or the default path."""
    if provider is None:
        return f"{_GITHUB_COPILOT_BASE_URL}/chat/completions"

    provider_type = provider.provider_type

    if provider_type == ProviderType.AZURE_OPENAI:
        base = provider.base_url or ""
        deployment = provider.azure_deployment or model
        api_version = provider.azure_api_version
        azure_deployments_path = "/openai/deployments/"
        if azure_deployments_path not in base:
            base = base.rstrip("/")
            return f"{base}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
        return f"{base.rstrip('/')}/chat/completions?api-version={api_version}"

    raw_url = provider.base_url or PROVIDER_DEFAULT_BASE_URLS.get(provider_type)
    if not raw_url:
        raise ValueError(
            f"Provider '{provider.name}' has no base_url configured."
        )
    return raw_url.rstrip("/") + "/chat/completions"


def _build_headers(provider: Provider | None, api_key: str) -> dict[str, str]:
    """Build HTTP headers for a chat request."""
    if provider is None:
        return {
            "Authorization": f"Bearer {api_key}",
            "content-type": "application/json",
        }
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
    return {
        "Authorization": f"Bearer {api_key}",
        "content-type": "application/json",
    }


# ── Main handler ─────────────────────────────────────────────────────────────


async def handle_chat(
    agent: Agent,
    session: ChatSession,
    user_message: str,
    github_user: str,
    github_token: str | None = None,
) -> AsyncGenerator[ChatEvent, None]:
    """Drive a single chat turn and stream SSE events.

    Yields:
        - ``session`` — session ID (first event, always sent)
        - ``delta``   — one per token chunk from the LLM
        - ``error``   — on LLM / provider failure
        - ``done``    — stream complete, includes usage and persisted message ID
    """
    session_id = str(session.id)

    # Always emit the session event first so the client knows which session
    # this conversation belongs to.
    yield _session_event(session_id)

    # ── Resolve provider & API key ────────────────────────────────────────
    provider: Provider | None = None
    api_key: str | None = github_token

    if agent.provider_id:
        try:
            prov = await Provider.get(PydanticObjectId(agent.provider_id))
            if prov:
                resolved_key = await token_manager.get_token_value(
                    prov.api_key_token_name
                )
                if resolved_key:
                    if prov.provider_type == ProviderType.GITHUB_COPILOT:
                        # Treat stored github_copilot token as the GitHub token
                        api_key = resolved_key
                    else:
                        provider = prov
                        api_key = resolved_key
        except Exception as exc:
            logger.warning("chat: provider resolution failed: %s", exc)

    if not api_key:
        yield _error_event(
            "No API key available — configure GITHUB_TOKEN or attach a provider."
        )
        return

    # ── Build system prompt ───────────────────────────────────────────────
    context_block = ""
    try:
        context_block = await build_chat_context(agent, github_user)
    except Exception as exc:
        logger.warning("chat: context build failed: %s", exc)

    chat_policy = (
        "You are in CHAT mode — a conversational interface. "
        "Do NOT execute tasks or use tools. "
        "Answer the user's questions based on your configuration, "
        "skills, available tools, and task history provided in the context below."
    )

    system_parts = [agent.system_prompt or "You are a helpful assistant.", chat_policy]
    if context_block:
        system_parts.append(context_block)
    system_prompt = "\n\n".join(system_parts)

    # ── Load conversation history ─────────────────────────────────────────
    history: list[ChatMessage] = (
        await ChatMessage.find({"session_id": session.id})
        .sort("created_at")
        .limit(_CONVERSATION_WINDOW)
        .to_list()
    )

    # ── Persist user message ──────────────────────────────────────────────
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=user_message,
    )
    await user_msg.insert()
    chat_messages_total.labels(role="user").inc()

    # ── Assemble messages array for LLM ──────────────────────────────────
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": user_message})

    # ── LLM streaming call ────────────────────────────────────────────────
    model = agent.model or settings.default_model
    url = _resolve_url(provider, model)
    headers = _build_headers(provider, api_key)
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    response_parts: list[str] = []
    usage_data: dict = {}
    start_time = datetime.now(UTC)

    try:
        async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
            async with client.stream(
                "POST", url, headers=headers, json=body
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[len("data:"):].lstrip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue

                    if "usage" in chunk and chunk["usage"]:
                        usage_data = chunk["usage"]

                    choices = chunk.get("choices") or []
                    if not choices:
                        continue

                    delta = choices[0].get("delta", {})
                    content_delta = delta.get("content")
                    if content_delta:
                        response_parts.append(content_delta)
                        yield _delta_event(content_delta)

    except Exception:
        logger.exception("chat: LLM call failed for session %s", session_id)
        yield _error_event("LLM request failed. Please try again.")
        return

    # ── Record duration metric ────────────────────────────────────────────
    elapsed = (datetime.now(UTC) - start_time).total_seconds()
    chat_response_duration_seconds.labels(model=model).observe(elapsed)

    # ── Persist assistant message ─────────────────────────────────────────
    final_text = "".join(response_parts)
    assistant_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=final_text,
        usage=usage_data or None,
    )
    await assistant_msg.insert()
    chat_messages_total.labels(role="assistant").inc()

    # ── Update session metadata ───────────────────────────────────────────
    session.message_count += 2  # user + assistant
    session.updated_at = datetime.now(UTC)
    if not session.title:
        # Auto-generate title from first message (truncate to 60 chars)
        session.title = user_message[:60] + ("…" if len(user_message) > 60 else "")
    await session.save()

    yield _done_event(usage_data, str(assistant_msg.id))
