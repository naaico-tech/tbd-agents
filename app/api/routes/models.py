"""API route to list available Copilot models with billing multipliers."""

from fastapi import APIRouter, Depends, Header

from app.api.deps import extract_token, get_current_user
from app.services.copilot_client import build_client

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models(
    _user=Depends(get_current_user),
    authorization: str | None = Header(None),
):
    """Return available models from the Copilot SDK with billing info."""
    token = extract_token(authorization)
    client = build_client(token)
    async with client as c:
        models = await c.list_models()
    return [m.to_dict() for m in models]
