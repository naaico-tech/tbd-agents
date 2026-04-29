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
from app.models.provider import (
    BYOK_HTTP_PROVIDER_TYPES,
    PROVIDER_DEFAULT_BASE_URLS,
    Provider,
    ProviderType,
)
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
            return (
                f"{base}/openai/deployments/{deployment}"
                f"/chat/completions?api-version={api_version}"
            )
        return f"{base.rstrip('/')}/chat/completions?api-version={api_version}"

    if provider_type == ProviderType.ANTHROPIC:
        # Anthropic uses the native Messages API, not an OpenAI-compatible
        # /chat/completions endpoint. The httpx path in handle_chat() only
        # supports OpenAI-style streaming, so reject Anthropic providers here
        # with a clear error rather than silently calling an invalid URL.
        raise ValueError(
            f"Provider '{provider.name}' uses Anthropic, which is not supported "
            "in chat mode (no OpenAI-compatible endpoint). Attach an OpenAI, "
            "Azure OpenAI, or Custom provider instead."
        )

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


# ── Auto-provider helpers ────────────────────────────────────────────────────


async def _resolve_auto_sub_providers(
    auto_provider: Provider,
) -> list[tuple[Provider, str, str]]:
    """Resolve ``(sub_provider, api_key, model)`` tuples for an AUTO provider.

    Returns entries sorted by ascending ``priority``, silently skipping any
    that are unavailable (DB miss, empty/missing API key, or unsupported
    provider type such as Anthropic).
    """
    results: list[tuple[Provider, str, str]] = []
    sorted_entries = sorted(auto_provider.aggregated_providers, key=lambda e: e.priority)

    for entry in sorted_entries:
        try:
            sub_prov = await Provider.get(PydanticObjectId(entry.provider_id))
        except Exception as exc:
            logger.warning(
                "chat: AUTO: failed to load sub-provider %s: %s", entry.provider_id, exc
            )
            continue

        if sub_prov is None:
            logger.warning("chat: AUTO: sub-provider %s not found in DB", entry.provider_id)
            continue

        if sub_prov.provider_type not in BYOK_HTTP_PROVIDER_TYPES:
            logger.warning(
                "chat: AUTO: sub-provider '%s' has unsupported type '%s' — skipping",
                sub_prov.name,
                sub_prov.provider_type,
            )
            continue

        if not sub_prov.api_key_token_name:
            logger.warning(
                "chat: AUTO: sub-provider '%s' has no api_key_token_name — skipping",
                sub_prov.name,
            )
            continue

        try:
            sub_key = await token_manager.get_token_value(sub_prov.api_key_token_name)
        except Exception as exc:
            logger.warning(
                "chat: AUTO: failed to get API key for sub-provider '%s': %s",
                sub_prov.name,
                exc,
            )
            continue

        if not sub_key:
            logger.warning(
                "chat: AUTO: API key for sub-provider '%s' is empty — skipping",
                sub_prov.name,
            )
            continue

        results.append((sub_prov, sub_key, entry.model))

    return results


async def _stream_from_provider(
    provider: Provider | None,
    api_key: str,
    model: str,
    messages: list[dict],
    session_id: str,
) -> AsyncGenerator[ChatEvent, None]:
    """Async generator for a single streaming LLM call.

    Yields:
        - ``{"type": "delta", "content": ...}`` — one per token chunk.
        - ``{"type": "_usage", "usage": {...}}`` — internal; caller extracts
          usage data and does **not** forward this event type to the client.

    Raises:
        httpx.HTTPStatusError: when the server returns HTTP >= 400.  This is
            raised *before* any delta/usage event is yielded, so the AUTO
            fallback loop can safely skip to the next sub-provider.
        httpx.RequestError: on connection or network failure.
        ValueError: if the provider configuration is invalid (e.g. an
            unsupported provider type reaches ``_resolve_url``).
    """
    url = _resolve_url(provider, model)
    headers = _build_headers(provider, api_key)
    body = {
        "model": model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            if response.status_code >= 400:
                body_bytes = await response.aread()
                body_text = body_bytes.decode(errors="replace")[:500]
                logger.error(
                    "chat: LLM HTTP %s for session %s url=%s body=%s",
                    response.status_code,
                    session_id,
                    url,
                    body_text,
                )
                response.raise_for_status()  # raises httpx.HTTPStatusError

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].lstrip()
                if payload == "[DONE]":
                    return
                try:
                    chunk = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if "usage" in chunk and chunk["usage"]:
                    yield {"type": "_usage", "usage": chunk["usage"]}

                choices = chunk.get("choices") or []
                if not choices:
                    continue

                delta = choices[0].get("delta", {})
                content_delta = delta.get("content")
                if content_delta:
                    yield _delta_event(content_delta)


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
    is_auto_provider = False
    auto_provider: Provider | None = None

    if agent.provider_id:
        try:
            prov = await Provider.get(PydanticObjectId(agent.provider_id))
            if prov:
                if prov.provider_type == ProviderType.AUTO:
                    # AUTO providers carry no top-level api_key_token_name —
                    # each sub-provider manages its own key.
                    is_auto_provider = True
                    auto_provider = prov
                else:
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

    if not is_auto_provider and not api_key:
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
    # Sort descending so we get the *most recent* _CONVERSATION_WINDOW messages,
    # then reverse to restore chronological order for the messages array.
    history: list[ChatMessage] = list(
        reversed(
            await ChatMessage.find({"session_id": session.id})
            .sort("-created_at")
            .limit(_CONVERSATION_WINDOW)
            .to_list()
        )
    )

    # ── Persist user message ──────────────────────────────────────────────
    user_msg = ChatMessage(
        session_id=session.id,
        role="user",
        content=user_message,
    )
    await user_msg.insert()
    chat_messages_total.labels(role="user").inc()

    # Update session metadata right after persisting the user message so that
    # session counts and the auto-title remain consistent even if the LLM call
    # fails before the assistant reply is written.
    session.message_count = (session.message_count or 0) + 1
    session.updated_at = datetime.now(UTC)
    if not (session.title or "").strip():
        session.title = user_message.strip()[:80] or "New Chat"
    await session.save()

    # ── Assemble messages array for LLM ──────────────────────────────────
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for h in history:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": user_message})

    # ── LLM streaming call ────────────────────────────────────────────────
    model = agent.model or settings.default_model
    response_parts: list[str] = []
    usage_data: dict = {}
    start_time = datetime.now(UTC)

    if is_auto_provider and auto_provider is not None:
        # ── AUTO: try sub-providers in ascending priority order ───────────
        try:
            sub_providers = await _resolve_auto_sub_providers(auto_provider)
        except Exception as exc:
            logger.exception(
                "chat: AUTO: failed to resolve sub-providers for session %s: %s",
                session_id,
                exc,
            )
            yield _error_event("AUTO provider configuration error. Please try again.")
            return

        if not sub_providers:
            yield _error_event(
                "AUTO provider has no available sub-providers configured."
            )
            return

        succeeded = False
        for sub_prov, sub_key, sub_model in sub_providers:
            gen = _stream_from_provider(sub_prov, sub_key, sub_model, messages, session_id)
            try:
                # Peek at the first item.  If the provider is unreachable or
                # returns HTTP >= 400, the generator raises *before* yielding
                # anything, so we can safely move on to the next sub-provider.
                first_item = await gen.__anext__()
            except StopAsyncIteration:
                logger.warning(
                    "chat: AUTO: sub-provider '%s' returned empty response — trying next",
                    sub_prov.name,
                )
                continue
            except Exception as exc:
                logger.warning(
                    "chat: AUTO: sub-provider '%s' failed (%s) — trying next",
                    sub_prov.name,
                    exc,
                )
                await gen.aclose()
                continue

            # First item received — process it, then stream the rest.
            if first_item.get("type") == "_usage":
                usage_data = first_item["usage"]
            elif first_item.get("type") == "delta":
                response_parts.append(first_item["content"])
                yield first_item

            try:
                async for item in gen:
                    if item.get("type") == "_usage":
                        usage_data = item["usage"]
                    elif item.get("type") == "delta":
                        response_parts.append(item["content"])
                        yield item
            except Exception as exc:
                logger.exception(
                    "chat: AUTO: sub-provider '%s' failed mid-stream for session %s: %s",
                    sub_prov.name,
                    session_id,
                    exc,
                )
                yield _error_event("LLM request failed mid-stream. Please try again.")
                return

            succeeded = True
            break

        if not succeeded:
            yield _error_event(
                "All AUTO sub-providers failed. Please try again later."
            )
            return

    else:
        # ── Single provider / default GitHub Copilot path ────────────────
        try:
            url = _resolve_url(provider, model)
            headers = _build_headers(provider, api_key)  # type: ignore[arg-type]
        except ValueError as exc:
            logger.warning(
                "chat: provider configuration error for session %s: %s", session_id, exc
            )
            yield _error_event(str(exc))
            return
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        try:
            async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=body
                ) as response:
                    if response.status_code >= 400:
                        body_bytes = await response.aread()
                        body_text = body_bytes.decode(errors="replace")[:500]
                        logger.error(
                            "chat: LLM HTTP %s for session %s url=%s body=%s",
                            response.status_code,
                            session_id,
                            url,
                            body_text,
                        )
                        yield _error_event("LLM request failed. Please try again.")
                        return
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[len("data:") :].lstrip()
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
    session.message_count += 1  # assistant message (user was already counted above)
    session.updated_at = datetime.now(UTC)
    await session.save()

    yield _done_event(usage_data, str(assistant_msg.id))
