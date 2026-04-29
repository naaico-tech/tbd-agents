from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.provider import BYOK_HTTP_PROVIDER_TYPES, Provider, ProviderType
from app.schemas.provider import ProviderCreate, ProviderResponse, ProviderUpdate

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _to_response(provider: Provider) -> ProviderResponse:
    return ProviderResponse(
        id=str(provider.id),
        name=provider.name,
        provider_type=provider.provider_type,
        api_key_token_name=provider.api_key_token_name,
        base_url=provider.base_url,
        azure_api_version=provider.azure_api_version,
        azure_deployment=provider.azure_deployment,
        description=provider.description,
        aggregated_providers=provider.aggregated_providers,
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


async def _validate_aggregated_providers(aggregated_providers: list) -> None:
    """Validate each aggregated provider entry for AUTO-type providers.

    Raises HTTPException(422) if any sub-provider:
    - does not exist in the database
    - is not a BYOK HTTP provider type (openai, azure_openai, custom)
    - is itself an AUTO provider (no nesting allowed)
    """
    for entry in aggregated_providers:
        try:
            sub_provider = await Provider.get(PydanticObjectId(entry.provider_id))
        except Exception:
            sub_provider = None
        if not sub_provider:
            raise HTTPException(
                status_code=422,
                detail=f"Aggregated provider '{entry.provider_id}' not found",
            )
        if sub_provider.provider_type not in BYOK_HTTP_PROVIDER_TYPES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Aggregated provider '{entry.provider_id}' has unsupported type "
                    f"'{sub_provider.provider_type}'. Must be one of: "
                    f"{', '.join(sorted(BYOK_HTTP_PROVIDER_TYPES))}"
                ),
            )
        if sub_provider.provider_type == ProviderType.AUTO:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Aggregated provider '{entry.provider_id}' cannot itself be an AUTO provider"
                    " (nesting not allowed)"
                ),
            )


@router.post("", response_model=ProviderResponse, status_code=201)
async def create_provider(body: ProviderCreate, _user=Depends(get_current_user)):
    """Create a new provider configuration."""
    existing = await Provider.find_one(Provider.name == body.name)
    if existing:
        raise HTTPException(status_code=409, detail=f"Provider '{body.name}' already exists")
    if body.provider_type == ProviderType.AUTO:
        await _validate_aggregated_providers(body.aggregated_providers)
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
    update_data = body.model_dump(exclude_unset=True)
    if update_data:
        if "aggregated_providers" in update_data:
            await _validate_aggregated_providers(body.aggregated_providers)
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
