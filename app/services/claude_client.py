"""Anthropic Claude SDK client factory.

Creates AsyncAnthropic client instances configured with the caller's API key.
Analogous to copilot_client.py but for the native Anthropic SDK.
"""

import logging

from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)


def build_claude_client(api_key: str) -> AsyncAnthropic:
    """Create an AsyncAnthropic client authenticated with the given API key.

    The returned client can be used directly for chat completions::

        client = build_claude_client(api_key)
        response = await client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            messages=[{"role": "user", "content": "Hello"}],
        )
    """
    return AsyncAnthropic(api_key=api_key)
