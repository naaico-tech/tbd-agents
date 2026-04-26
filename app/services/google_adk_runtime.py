from __future__ import annotations

import inspect
import json
import re
from collections.abc import Awaitable, Callable
from copy import deepcopy
from functools import cached_property
from typing import Any

from google.adk.models.google_llm import Gemini
from google.adk.tools.base_tool import BaseTool
from google.genai import Client, types

from app.config import settings
from app.models.provider import Provider, ProviderType

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

_GOOGLE_ADK_MODEL_PAGE_SIZE = 100
_IDENTIFIER_SANITIZE_RE = re.compile(r"\W+")

ToolExecutor = Callable[[dict[str, Any]], Awaitable[Any] | Any]


def google_adk_provider_requires_api_key(provider: Provider) -> bool:
    """Return whether a Google ADK provider must resolve a Gemini API key."""
    return not bool(getattr(provider, "google_use_vertex_ai", False))


def validate_google_adk_provider_config(provider: Any) -> None:
    """Validate Google ADK provider settings that should fail fast at config time."""
    if getattr(provider, "provider_type", None) != ProviderType.GOOGLE_ADK:
        return

    if not bool(getattr(provider, "google_use_vertex_ai", False)):
        return

    missing_fields = [
        field_name
        for field_name, value in (
            ("google_cloud_project", getattr(provider, "google_cloud_project", None)),
            ("google_cloud_location", getattr(provider, "google_cloud_location", None)),
        )
        if not value
    ]
    if missing_fields:
        joined = ", ".join(missing_fields)
        provider_name = getattr(provider, "name", "google_adk")
        raise ValueError(
            f"Google ADK provider '{provider_name}' is configured for Vertex AI "
            f"but is missing required field(s): {joined}"
        )


def resolve_google_adk_session_id(
    *,
    app_name: str,
    user_id: str,
    fallback_session_id: str,
    persisted_session: dict[str, Any] | None = None,
) -> str:
    """Prefer the persisted ADK session id over shared workflow session ids."""
    session_data = (persisted_session or {}).get("session")
    if not isinstance(session_data, dict):
        return fallback_session_id

    if session_data.get("app_name") != app_name or session_data.get("user_id") != user_id:
        return fallback_session_id

    session_id = session_data.get("id")
    if isinstance(session_id, str) and session_id.strip():
        return session_id
    return fallback_session_id


def build_google_adk_agent_name(agent_id: str, *, prefix: str = "tbd-agent") -> str:
    """Build a stable ADK-safe agent name from a workflow agent id."""
    raw_name = prefix if not agent_id else f"{prefix}-{agent_id}"
    normalized = _IDENTIFIER_SANITIZE_RE.sub("_", raw_name.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")

    if not normalized:
        return "adk_agent"
    if normalized[0].isdigit():
        normalized = f"adk_{normalized}"
    if normalized.isidentifier():
        return normalized

    fallback = "".join(char if char == "_" or char.isalnum() else "_" for char in normalized)
    fallback = re.sub(r"_+", "_", fallback).strip("_") or "adk_agent"
    if fallback[0].isdigit():
        fallback = f"adk_{fallback}"
    return fallback


def _clip_tool_description(text: str | None) -> str:
    if not text:
        return ""
    max_chars = settings.tool_definition_description_max_chars
    text = str(text).strip()
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3].rstrip() + "..."


def sanitize_google_adk_schema(obj: Any) -> Any:
    """Trim JSON schema fields to the subset accepted by Google ADK."""
    if isinstance(obj, dict):
        sanitized: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "properties" and isinstance(value, dict):
                property_map = {
                    prop_name: sanitize_google_adk_schema(prop_schema)
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
            cleaned = sanitize_google_adk_schema(value)
            if cleaned in ({}, [], ""):
                if key in {"properties", "required"}:
                    sanitized[key] = cleaned
                continue
            sanitized[key] = cleaned
        return sanitized
    if isinstance(obj, list):
        return [
            item
            for item in (sanitize_google_adk_schema(item) for item in obj)
            if item not in ({}, [], "")
        ]
    return obj


def normalize_google_adk_tool_result(result: Any) -> dict[str, Any]:
    """Convert tool outputs into JSON-like payloads for ADK function responses."""
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        return {"result": result}
    if result is None:
        return {"result": ""}
    if isinstance(result, (bool, int, float)):
        return {"result": result}
    if isinstance(result, str):
        stripped = result.strip()
        if stripped and stripped[0] in "[{":
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                return {"result": result}
            if isinstance(parsed, dict):
                return parsed
            return {"result": parsed}
        return {"result": result}
    return {"result": str(result)}


def stringify_google_adk_tool_result(result: Any) -> str:
    """Render normalized ADK tool output for workflow logs."""
    normalized = normalize_google_adk_tool_result(result)
    return json.dumps(normalized, ensure_ascii=False, default=str)


def build_google_adk_client_config(
    provider: Provider,
    api_key: str | None,
) -> dict[str, Any]:
    """Resolve explicit Google ADK client settings from a provider config."""
    validate_google_adk_provider_config(provider)

    if google_adk_provider_requires_api_key(provider) and not api_key:
        raise ValueError(f"Google ADK provider '{provider.name}' requires a stored Gemini API key")

    use_vertex_ai = bool(provider.google_use_vertex_ai)
    project = provider.google_cloud_project
    location = provider.google_cloud_location

    return {
        "api_key": api_key,
        "use_vertex_ai": use_vertex_ai,
        "project": project,
        "location": location,
        "base_url": provider.base_url,
    }


def build_google_adk_runtime_config(
    provider: Provider,
    api_key: str | None,
    model: str,
) -> dict[str, Any]:
    """Resolve explicit Google ADK runtime settings from a provider config."""
    config = build_google_adk_client_config(provider, api_key)
    config["model"] = model
    return config


def build_google_adk_client_kwargs(
    runtime_config: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    retry_options: Any = None,
    api_version: str | None = None,
) -> dict[str, Any]:
    """Build Google GenAI client kwargs from normalized runtime settings."""
    http_options = types.HttpOptions(
        headers=headers,
        retry_options=retry_options,
        base_url=runtime_config.get("base_url"),
        api_version=api_version,
    )
    kwargs: dict[str, Any] = {"http_options": http_options}
    if runtime_config.get("use_vertex_ai"):
        kwargs["vertexai"] = True
        kwargs["project"] = runtime_config.get("project")
        kwargs["location"] = runtime_config.get("location")
    else:
        kwargs["api_key"] = runtime_config.get("api_key")
    return kwargs


def build_google_adk_client(
    runtime_config: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    retry_options: Any = None,
    api_version: str | None = None,
) -> Client:
    """Create a Google GenAI client from normalized runtime settings."""
    return Client(
        **build_google_adk_client_kwargs(
            runtime_config,
            headers=headers,
            retry_options=retry_options,
            api_version=api_version,
        )
    )


def extract_google_adk_text(response: Any) -> str:
    """Collect visible text parts from a Google GenAI response object."""
    parts: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False):
                parts.append(text)
    return "".join(parts)


def google_adk_usage_to_dict(usage_metadata: Any) -> dict[str, int]:
    """Normalize Google usage metadata into a compact API-friendly shape."""
    prompt_tokens = int(getattr(usage_metadata, "prompt_token_count", 0) or 0)
    tool_prompt_tokens = int(getattr(usage_metadata, "tool_use_prompt_token_count", 0) or 0)
    completion_tokens = int(getattr(usage_metadata, "candidates_token_count", 0) or 0)
    cached_tokens = int(getattr(usage_metadata, "cached_content_token_count", 0) or 0)
    total_tokens = prompt_tokens + tool_prompt_tokens + completion_tokens

    usage: dict[str, int] = {}
    if prompt_tokens or tool_prompt_tokens:
        usage["prompt_tokens"] = prompt_tokens + tool_prompt_tokens
    if completion_tokens:
        usage["completion_tokens"] = completion_tokens
    if total_tokens:
        usage["total_tokens"] = total_tokens
    if cached_tokens:
        usage["cached_tokens"] = cached_tokens
    return usage


def format_google_adk_error(
    exc: Exception,
    *,
    provider: Provider,
    action: str,
    model: str | None = None,
) -> str:
    """Return a provider-specific, user-facing Google ADK error message."""
    if isinstance(exc, ValueError):
        return str(exc)

    status = int(getattr(exc, "status", 0) or 0)
    prefix = f"Google ADK {action} failed for provider '{provider.name}'"

    if status in {401, 403}:
        return f"{prefix}: invalid Gemini credentials or insufficient Vertex AI permissions."
    if status == 404 and model:
        return f"{prefix}: model '{model}' was not found or is not available."
    if status == 404:
        return f"{prefix}: the requested Google resource was not found."
    if status == 429:
        return f"{prefix}: Google rate limited the request. Please retry shortly."
    if status >= 500:
        return f"{prefix}: Google returned a temporary server error ({status})."

    detail = getattr(exc, "message", None) or str(exc)
    return f"{prefix}: {detail}"


def google_adk_model_id(raw_name: str | None) -> str:
    """Normalize Google model names into stable API IDs."""
    if not raw_name:
        return ""
    marker = "/models/"
    if marker in raw_name:
        return raw_name.split(marker, 1)[1]
    if raw_name.startswith("models/"):
        return raw_name.split("/", 1)[1]
    return raw_name


def serialize_google_adk_model(model: types.Model) -> dict[str, Any]:
    """Convert a Google model entry into the app's API response shape."""
    model_id = google_adk_model_id(model.name)
    return {
        "id": model_id,
        "name": model.display_name or model_id,
        "provider_type": ProviderType.GOOGLE_ADK,
        "description": model.description,
        "input_token_limit": model.input_token_limit,
        "output_token_limit": model.output_token_limit,
        "supported_actions": list(model.supported_actions or []),
    }


async def list_google_adk_models(runtime_config: dict[str, Any]) -> list[dict[str, Any]]:
    """List chat-capable Google models for a configured ADK provider."""
    client = build_google_adk_client(runtime_config)
    try:
        pager = await client.aio.models.list(
            config=types.ListModelsConfig(page_size=_GOOGLE_ADK_MODEL_PAGE_SIZE)
        )
        models: list[dict[str, Any]] = []
        async for model in pager:
            supported_actions = set(model.supported_actions or [])
            if "generateContent" not in supported_actions:
                continue
            models.append(serialize_google_adk_model(model))
        return sorted(models, key=lambda item: item["id"])
    finally:
        await client.aio.aclose()
        client.close()


class ConfiguredGemini(Gemini):
    """Gemini ADK model wrapper with explicit per-provider auth configuration."""

    api_key: str | None = None
    use_vertex_ai: bool = False
    project: str | None = None
    location: str | None = None

    @cached_property
    def api_client(self) -> Client:
        kwargs = self._build_client_kwargs()
        return Client(**kwargs)

    @cached_property
    def _live_api_client(self) -> Client:
        kwargs = self._build_client_kwargs(api_version=self._live_api_version)
        return Client(**kwargs)

    def _build_client_kwargs(self, api_version: str | None = None) -> dict[str, Any]:
        return build_google_adk_client_kwargs(
            {
                "api_key": self.api_key,
                "use_vertex_ai": self.use_vertex_ai,
                "project": self.project,
                "location": self.location,
                "base_url": self.base_url,
            },
            headers=self._tracking_headers(),
            retry_options=self.retry_options,
            api_version=api_version,
        )


def build_google_adk_model(runtime_config: dict[str, Any]) -> ConfiguredGemini:
    """Create a configured Gemini model instance for Google ADK."""
    return ConfiguredGemini(
        model=runtime_config["model"],
        base_url=runtime_config.get("base_url"),
        api_key=runtime_config.get("api_key"),
        use_vertex_ai=runtime_config.get("use_vertex_ai", False),
        project=runtime_config.get("project"),
        location=runtime_config.get("location"),
    )


async def build_google_adk_session_service(
    *,
    app_name: str,
    user_id: str,
    session_id: str,
    persisted_session: dict[str, Any] | None = None,
) -> tuple[Any, bool]:
    """Create an in-memory ADK session service, restoring prior session state when available."""
    from google.adk.sessions import InMemorySessionService
    from google.adk.sessions.session import Session

    session_service = InMemorySessionService()

    if persisted_session:
        try:
            restored_session = Session.model_validate(persisted_session["session"])
            if (
                restored_session.app_name == app_name
                and restored_session.user_id == user_id
                and restored_session.id == session_id
            ):
                session_service.sessions.setdefault(app_name, {}).setdefault(user_id, {})[
                    session_id
                ] = restored_session

                app_state = persisted_session.get("app_state") or {}
                if isinstance(app_state, dict) and app_state:
                    session_service.app_state.setdefault(app_name, {}).update(deepcopy(app_state))

                user_state = persisted_session.get("user_state") or {}
                if isinstance(user_state, dict) and user_state:
                    session_service.user_state.setdefault(app_name, {}).setdefault(
                        user_id, {}
                    ).update(deepcopy(user_state))

                return session_service, True
        except Exception:
            pass

    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
    )
    return session_service, False


def dump_google_adk_session_service(
    session_service: Any,
    *,
    app_name: str,
    user_id: str,
    session_id: str,
) -> dict[str, Any] | None:
    """Serialize the active ADK session so it can be restored in a later worker run."""
    session = (
        getattr(session_service, "sessions", {}).get(app_name, {}).get(user_id, {}).get(session_id)
    )
    if session is None:
        return None

    return {
        "app_name": app_name,
        "session": session.model_dump(mode="json"),
        "session_id": session.id,
        "app_state": deepcopy(getattr(session_service, "app_state", {}).get(app_name, {})),
        "user_id": user_id,
        "user_state": deepcopy(
            getattr(session_service, "user_state", {}).get(app_name, {}).get(user_id, {})
        ),
    }


class GoogleAdkTool(BaseTool):
    """Structured ADK tool backed by an async executor."""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        schema: dict[str, Any] | None,
        executor: ToolExecutor,
    ):
        super().__init__(
            name=name,
            description=_clip_tool_description(description),
        )
        normalized_schema = sanitize_google_adk_schema(
            schema or {"type": "object", "properties": {}}
        )
        normalized_schema.setdefault("type", "object")
        normalized_schema.setdefault("properties", {})
        self._schema = normalized_schema
        self._executor = executor

    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return types.FunctionDeclaration.model_validate(
            {
                "name": self.name,
                "description": self.description,
                "parameters": self._schema,
            }
        )

    async def run_async(self, *, args: dict[str, Any], tool_context) -> dict[str, Any]:
        result = self._executor(args)
        if inspect.isawaitable(result):
            result = await result
        return normalize_google_adk_tool_result(result)
