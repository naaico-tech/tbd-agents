from datetime import datetime

from pydantic import BaseModel

from app.models.provider import ProviderType


class ProviderCreate(BaseModel):
    name: str
    provider_type: ProviderType
    api_key_token_name: str
    base_url: str | None = None
    auth_type: str = "x-api-key"
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str | None = None
    description: str = ""


class ProviderUpdate(BaseModel):
    name: str | None = None
    provider_type: ProviderType | None = None
    api_key_token_name: str | None = None
    base_url: str | None = None
    auth_type: str | None = None
    azure_api_version: str | None = None
    azure_deployment: str | None = None
    description: str | None = None


class ProviderResponse(BaseModel):
    id: str
    name: str
    provider_type: ProviderType
    api_key_token_name: str
    base_url: str | None
    auth_type: str = "x-api-key"
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str | None = None
    description: str
    created_at: datetime
    updated_at: datetime
