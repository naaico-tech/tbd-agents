from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.provider import BYOK_HTTP_PROVIDER_TYPES, AggregatedProviderEntry, ProviderType


class AggregatedProviderEntrySchema(BaseModel):
    provider_id: str
    model: str
    priority: int = 0


class ProviderCreate(BaseModel):
    name: str
    provider_type: ProviderType
    api_key_token_name: str | None = None
    base_url: str | None = None
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str | None = None
    description: str = ""
    aggregated_providers: list[AggregatedProviderEntrySchema] = []

    @model_validator(mode="after")
    def _validate_provider_config(self) -> "ProviderCreate":
        if self.provider_type == ProviderType.AUTO:
            if not self.aggregated_providers:
                raise ValueError(
                    "AUTO provider requires at least one entry in aggregated_providers"
                )
            for entry in self.aggregated_providers:
                # Resolve provider_type from provider_id is not possible at schema
                # validation time (no DB access), so we enforce it in the route handler.
                pass
        else:
            if not self.api_key_token_name:
                raise ValueError(
                    "api_key_token_name is required for non-AUTO provider types"
                )
        return self


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: ProviderType | None = None
    api_key_token_name: str | None = None
    base_url: str | None = None
    azure_api_version: str | None = None
    azure_deployment: str | None = None
    description: str | None = None
    aggregated_providers: list[AggregatedProviderEntrySchema] | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: ProviderType
    api_key_token_name: str | None
    base_url: str | None
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str | None = None
    description: str
    aggregated_providers: list[AggregatedProviderEntry] = []
    created_at: datetime
    updated_at: datetime
