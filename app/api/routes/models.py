"""API route to list available Copilot models with billing multipliers."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.api.deps import extract_optional_token, get_current_user
from app.models.provider import Provider, ProviderType
from app.services import token_manager
from app.services.copilot_client import build_client

router = APIRouter(prefix="/api/models", tags=["models"])


async def _resolve_models_token(
    authorization: str | None,
    provider_id: str | None,
) -> str:
    token = extract_optional_token(authorization)

    if provider_id:
        try:
            provider = await Provider.get(PydanticObjectId(provider_id))
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid provider_id") from exc

        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        if provider.provider_type != ProviderType.GITHUB_COPILOT:
            raise HTTPException(
                status_code=400,
                detail="provider_id must reference a github_copilot provider",
            )

        token = await token_manager.get_token_value(provider.api_key_token_name)
        if not token:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Provider '{provider.name}' token '{provider.api_key_token_name}' "
                    "was not found in the token store"
                ),
            )

    if not token:
        raise HTTPException(
            status_code=400,
            detail=(
                "GitHub Copilot model listing requires a GitHub token; provide an "
                "Authorization header, set GITHUB_TOKEN, or select a github_copilot provider"
            ),
        )

    return token


@router.get("")
async def list_models(
    _user=Depends(get_current_user),
    authorization: str | None = Header(None),
    provider_id: str | None = Query(None),
):
    """Return available models from the Copilot SDK with billing info."""
    token = await _resolve_models_token(authorization, provider_id)
    client = build_client(token)
    async with client as c:
        models = await c.list_models()
    return [m.to_dict() for m in models]
