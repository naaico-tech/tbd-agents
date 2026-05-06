from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document, Indexed
from pydantic import Field


class ProviderType(StrEnum):
    GITHUB_COPILOT = "github_copilot"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"


# Default base URLs for built-in provider types
PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    ProviderType.OPENAI: "https://api.openai.com/v1",
    ProviderType.ANTHROPIC: "https://api.anthropic.com/v1",
}


class Provider(Document):
    """A named AI provider configuration that can be attached to an agent.

    Stores provider type, a reference to an API key in the token store,
    and an optional base URL override. When an agent has a ``provider_id``
    set, the agent engine resolves the API key and routes execution through
    the corresponding provider backend.

    - ``github_copilot``: uses the stored key as the GitHub PAT for the SDK.
    - ``anthropic``: uses the Claude Agent SDK (``beta.agents``/``beta.sessions``).
      When ``base_url`` is set and the ``CLAUDE_SDK_THIRD_PARTY_PROVIDERS_ENABLED``
      flag is ``True``, all SDK requests are routed through that URL. This enables
      third-party Anthropic-compatible gateways such as LiteLLM (self-hosted) to
      serve as the backend. The gateway must implement the full Anthropic beta API
      (``/v1/environments``, ``/v1/agents``, ``/v1/sessions``) to be compatible.
      If omitted, the default ``https://api.anthropic.com`` endpoint is used.
    - ``openai`` / ``azure_openai`` / ``custom``: issues requests directly to the
      provider's OpenAI-compatible chat completions endpoint using the resolved
      API key. ``base_url`` overrides the default endpoint.
    """

    name: Indexed(str, unique=True)
    provider_type: ProviderType
    api_key_token_name: str  # name of a Token document in the token store
    base_url: str | None = None  # required for azure_openai and custom types
    azure_api_version: str = "2024-12-01-preview"  # Azure OpenAI API version
    azure_deployment: str | None = None  # Azure deployment name (defaults to workflow model)
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "providers"
