"""GitHub Copilot SDK client factory.

Creates CopilotClient instances configured with the caller's GitHub token.
Each client spawns a Copilot CLI subprocess (bundled with the SDK).
"""

import logging
import os

from copilot import CopilotClient, SubprocessConfig

from app.config import settings

logger = logging.getLogger(__name__)


def build_client(github_token: str | None) -> CopilotClient:
    """Create a CopilotClient that authenticates with the given GitHub token.

    The returned client should be used as an async context manager::

        async with build_client(token) as client:
            async with await client.create_session(...) as session:
                ...
    """
    if not github_token:
        raise ValueError(
            "GitHub token is required for default Copilot execution; configure GITHUB_TOKEN or attach a github_copilot provider with a stored token"
        )

    env = dict(os.environ)

    # TelemetryConfig is a TypedDict on SubprocessConfig
    telemetry = None
    if settings.otel_http_endpoint:
        telemetry = {
            "otlp_endpoint": settings.otel_http_endpoint,
            "exporter_type": "otlp-http",
            "source_name": "tbd-agents-sdk",
            "capture_content": False,
        }

    config = SubprocessConfig(
        github_token=github_token,
        use_stdio=True,
        env=env,
        telemetry=telemetry,
    )
    return CopilotClient(config)
