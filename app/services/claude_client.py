"""Anthropic Claude Agent SDK client factory.

Creates AsyncAnthropic client instances configured with the caller's API key.
The client provides access to the Claude Agent SDK beta APIs (environments,
agents, sessions) which handle the full agentic loop server-side — analogous
to how ``copilot_client.py`` builds a ``CopilotClient``.

Third-party gateway compatibility
----------------------------------
Anthropic's own API authenticates via ``x-api-key`` (``api_key`` param).
Gateways like OpenRouter use ``Authorization: Bearer`` (``auth_token`` param).
When *base_url* is set to a non-Anthropic URL, this module automatically
switches to Bearer-token auth so the request is accepted by the gateway.

OpenRouter example::

    provider.base_url = "https://openrouter.ai/api"
    provider.api_key  = "<your-openrouter-key>"

OpenRouter will then route the Agent SDK calls to whichever Claude model is
specified by the workflow (using ``ANTHROPIC_DEFAULT_SONNET_MODEL`` /
``ANTHROPIC_DEFAULT_OPUS_MODEL`` env overrides if needed).
"""

import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)

_ANTHROPIC_DOMAIN = "anthropic.com"


def build_claude_client(api_key: str, base_url: str | None = None) -> AsyncAnthropic:
    """Create an AsyncAnthropic client authenticated with the given API key.

    When *base_url* is provided the client routes all requests through that
    URL, enabling third-party gateways (OpenRouter, LiteLLM, …) to be used in
    place of the default ``https://api.anthropic.com`` endpoint.

    Auth-header selection:

    * **Direct Anthropic** (no *base_url*, or *base_url* contains
      ``anthropic.com``): sends ``x-api-key: <api_key>``.
    * **Third-party gateway** (*base_url* set to a non-Anthropic host):
      sends ``Authorization: Bearer <api_key>`` and clears ``api_key`` so the
      SDK does not also send the ``x-api-key`` header (which gateways reject).

    The returned client exposes the Claude Agent SDK via ``client.beta``::

        client = build_claude_client(api_key)
        env = await client.beta.environments.create(name="my-env")
        agent = await client.beta.agents.create(model="claude-sonnet-4-6", name="my-agent")
        session = await client.beta.sessions.create(
            environment_id=env.id,
            agent={"type": "agent", "id": agent.id, "version": agent.version},
        )
    """
    is_anthropic_direct = not base_url or _ANTHROPIC_DOMAIN in base_url

    if is_anthropic_direct:
        kwargs: dict = {"api_key": api_key}
    else:
        # Third-party gateways (OpenRouter, LiteLLM, …) authenticate via
        # Authorization: Bearer, not x-api-key.  Set api_key="" to prevent
        # the SDK from emitting both headers simultaneously.
        kwargs = {"auth_token": api_key, "api_key": ""}
        logger.debug("Claude client: using Bearer auth for third-party gateway %s", base_url)

    if base_url:
        kwargs["base_url"] = base_url

    return AsyncAnthropic(**kwargs)
