"""GitHub Copilot SDK client factory.

Creates CopilotClient instances configured with the caller's GitHub token.
Each client spawns a Copilot CLI subprocess (bundled with the SDK).
"""

import logging
import os

from copilot import CopilotClient, SubprocessConfig

logger = logging.getLogger(__name__)


def build_client(github_token: str) -> CopilotClient:
    """Create a CopilotClient that authenticates with the given GitHub token.

    The returned client should be used as an async context manager::

        async with build_client(token) as client:
            async with await client.create_session(...) as session:
                ...
    """
    env = dict(os.environ)
    config = SubprocessConfig(
        github_token=github_token,
        use_stdio=True,
        env=env,
    )
    return CopilotClient(config)
