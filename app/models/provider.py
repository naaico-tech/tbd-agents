from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document, Indexed
from pydantic import BaseModel, Field


class ProviderType(StrEnum):
    GITHUB_COPILOT = "github_copilot"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"
    AUTO = "auto"


# Provider types that use the HTTP /chat/completions path (BYOK HTTP).
# These are the only types allowed as sub-providers inside an AUTO provider.
BYOK_HTTP_PROVIDER_TYPES: frozenset[ProviderType] = frozenset({
    ProviderType.OPENAI,
    ProviderType.AZURE_OPENAI,
    ProviderType.CUSTOM,
})

# Default base URLs for built-in provider types
PROVIDER_DEFAULT_BASE_URLS: dict[str, str] = {
    ProviderType.OPENAI: "https://api.openai.com/v1",
    ProviderType.ANTHROPIC: "https://api.anthropic.com/v1",
}


class AggregatedProviderEntry(BaseModel):
    """A single sub-provider entry within an AUTO provider.

    ``priority`` controls the order in which sub-providers are tried:
    lower values are tried first (0 = highest priority).
    """

    provider_id: str
    model: str
    priority: int = 0


class Provider(Document):
    """A named AI provider configuration that can be attached to an agent.

    Stores provider type, a reference to an API key in the token store,
    and an optional base URL override. When an agent has a ``provider_id``
    set, the agent engine resolves the API key and routes execution through
    the corresponding provider backend.

    - ``github_copilot``: uses the stored key as the GitHub PAT for the SDK.
    - ``openai`` / ``anthropic`` / ``azure_openai`` / ``custom``: issues
      requests directly to the provider's OpenAI-compatible chat completions
      endpoint using the resolved API key.
    - ``auto``: aggregates multiple BYOK HTTP sub-providers. The agent engine
      tries them in ascending ``priority`` order, falling back to the next
      entry on retryable failures. ``api_key_token_name`` is unused for this
      type; use ``aggregated_providers`` instead.
    """

    name: Indexed(str, unique=True)
    provider_type: ProviderType
    api_key_token_name: str | None = None  # not used for AUTO type
    base_url: str | None = None  # required for azure_openai and custom types
    azure_api_version: str = "2024-12-01-preview"  # Azure OpenAI API version
    azure_deployment: str | None = None  # Azure deployment name (defaults to workflow model)
    description: str = ""
    aggregated_providers: list[AggregatedProviderEntry] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "providers"
