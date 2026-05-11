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

    Provider routing decision table
    --------------------------------
    +---------------------------------+------------------------------------------+
    | Provider type / condition       | Execution path                           |
    +=================================+==========================================+
    | ``github_copilot``              | Copilot SDK (GitHub Copilot infra)       |
    +---------------------------------+------------------------------------------+
    | ``anthropic`` + no ``base_url`` | Claude Agent SDK — server-side agentic   |
    |                                 | loop on Anthropic infrastructure         |
    |                                 | (``/v1/environments``, ``/v1/agents``)   |
    +---------------------------------+------------------------------------------+
    | ``anthropic`` + ``base_url``    | Anthropic messages API — client-side     |
    | set (gateway mode)              | agentic loop via ``messages.create``.    |
    |                                 | Works with OpenRouter, LiteLLM, and any  |
    |                                 | gateway that implements ``/v1/messages`` |
    +---------------------------------+------------------------------------------+
    | ``openai`` / ``azure_openai``   | OpenAI-compatible chat completions loop  |
    | / ``custom``                    | via ``/v1/chat/completions``             |
    +---------------------------------+------------------------------------------+

    - ``github_copilot``: uses the stored key as the GitHub PAT for the SDK.
    - ``anthropic``: when ``base_url`` is **not** set, uses the Claude Agent SDK
      (``beta.agents`` / ``beta.sessions``) on the default Anthropic endpoint.
      When ``base_url`` **is** set, the engine routes through the Anthropic
      messages API (``messages.create``) with a client-side agentic loop so the
      request targets the gateway — third-party gateways only expose
      ``/v1/messages``, not the SDK beta endpoints.
    - ``openai`` / ``azure_openai`` / ``custom``: issues requests directly to the
      provider's OpenAI-compatible chat completions endpoint using the resolved
      API key. ``base_url`` overrides the default endpoint.
    """

    name: Indexed(str, unique=True)
    provider_type: ProviderType
    api_key_token_name: str  # name of a Token document in the token store
    base_url: str | None = None  # required for azure_openai and custom types
    # Auth header style used when base_url is set for the anthropic provider type.
    # "x-api-key" (default) — direct Anthropic API key header.
    # "bearer"              — Authorization: Bearer <key> for OpenRouter/LiteLLM.
    auth_type: str = "x-api-key"
    azure_api_version: str = "2024-12-01-preview"  # Azure OpenAI API version
    azure_deployment: str | None = None  # Azure deployment name (defaults to workflow model)
    description: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "providers"
