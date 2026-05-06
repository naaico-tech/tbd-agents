from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.provider import Provider
from app.schemas.provider import ProviderCreate, ProviderResponse, ProviderUpdate

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _to_response(provider: Provider) -> ProviderResponse:
    return ProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_type=provider.provider_type,
        api_key_token_name=provider.api_key_token_name,
        base_url=provider.base_url,
        auth_type=provider.auth_type,
        azure_api_version=provider.azure_api_version,
        azure_deployment=provider.azure_deployment,
        description=provider.description,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(body: ProviderCreate, _user=Depends(get_current_user)):
    """Create a new provider configuration."""
    existing = await Provider.find_one(Provider.name == body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider '{body.name}' already exists")
    provider = Provider(**body.model_dump())
    await provider.insert()
    return _to_response(provider)


@router.get("", response_model=list[ProviderResponse])
async def list_providers(_user=Depends(get_current_user)):
    """List all configured providers."""
    providers = await Provider.find_all().to_list()
    return [_to_response(p) for p in providers]


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(provider_id: str, _user=Depends(get_current_user)):
    """Get a single provider by ID."""
    provider = await Provider.get(PydanticObjectId(provider_id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return _to_response(provider)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str, body: ProviderUpdate, _user=Depends(get_current_user)
):
    """Update a provider's configuration."""
    provider = await Provider.get(PydanticObjectId(provider_id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    update_data = body.model_dump(exclude_none=True)
    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await provider.set(update_data)
    return _to_response(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, _user=Depends(get_current_user)):
    """Delete a provider configuration."""
    provider = await Provider.get(PydanticObjectId(provider_id))
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    await provider.delete()
