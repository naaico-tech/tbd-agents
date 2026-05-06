"""Anthropic Claude Agent SDK client factory.

Creates AsyncAnthropic client instances configured with the caller's API key.
The client provides access to the Claude Agent SDK beta APIs (environments,
agents, sessions) which handle the full agentic loop server-side — analogous
to how ``copilot_client.py`` builds a ``CopilotClient``.

Auth header types
-----------------
``x-api-key`` (default)
    Standard Anthropic direct authentication — sends the API key in the
    ``x-api-key`` request header.  Use when calling ``api.anthropic.com``
    directly.

``bearer``
    Sends the API key as ``Authorization: Bearer <key>``.  Required for
    third-party gateways such as OpenRouter (``https://openrouter.ai/api``)
    and most LiteLLM deployments that forward to OpenRouter or other
    providers.  The SDK's ``api_key`` field is set to an empty string so
    the ``x-api-key`` header is not also emitted.
"""

import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


def build_claude_client(
    api_key: str,
    base_url: str | None = None,
    auth_type: str = "x-api-key",
) -> AsyncAnthropic:
    """Create an AsyncAnthropic client for the Claude Agent SDK.

    Args:
        api_key:   The API key (or token) used to authenticate.
        base_url:  Optional override for the API root URL.  When set,
                   all SDK requests are routed through this URL instead
                   of the default ``https://api.anthropic.com``.
        auth_type: ``"x-api-key"`` (default) or ``"bearer"``.  Controls
                   which HTTP auth header carries *api_key*.

    The returned client exposes the Claude Agent SDK via ``client.beta``::

        client = build_claude_client(api_key)
        env    = await client.beta.environments.create(name="my-env")
        agent  = await client.beta.agents.create(model="claude-sonnet-4-6", name="a")
        session = await client.beta.sessions.create(
            environment_id=env.id,
            agent={"type": "agent", "id": agent.id, "version": agent.version},
        )
    """
    if auth_type == "bearer":
        # Gateways like OpenRouter authenticate via Authorization: Bearer.
        # Clear api_key so the SDK does not also emit the x-api-key header.
        kwargs: dict = {"auth_token": api_key, "api_key": ""}
        logger.debug("Claude client: using Bearer auth (base_url=%s)", base_url)
    else:
        kwargs = {"api_key": api_key}

    if base_url:
        kwargs["base_url"] = base_url

    return AsyncAnthropic(**kwargs)
