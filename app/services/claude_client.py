"""Anthropic Claude Agent SDK client factory.

Creates AsyncAnthropic client instances configured with the caller's API key.
The client provides access to the Claude Agent SDK beta APIs (environments,
agents, sessions) which handle the full agentic loop server-side — analogous
to how ``copilot_client.py`` builds a ``CopilotClient``.
"""

import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


def build_claude_client(api_key: str, base_url: str | None = None) -> AsyncAnthropic:
    """Create an AsyncAnthropic client authenticated with the given API key.

    When *base_url* is provided the client routes all requests through that URL,
    enabling third-party Anthropic-compatible gateways (e.g. LiteLLM) to be
    used in place of the default ``https://api.anthropic.com`` endpoint.

    The returned client exposes the Claude Agent SDK via ``client.beta``::

        client = build_claude_client(api_key)
        env = await client.beta.environments.create(name="my-env")
        agent = await client.beta.agents.create(model="claude-sonnet-4-6", name="my-agent")
        session = await client.beta.sessions.create(
            environment_id=env.id,
            agent={"type": "agent", "id": agent.id, "version": agent.version},
        )
    """
    kwargs: dict = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncAnthropic(**kwargs)
