from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.models.token import Token
from app.schemas.token import TokenCreate, TokenResponse, TokenUpdate
from app.services import token_manager

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


def _to_response(token: Token) -> TokenResponse:
    return TokenResponse(
        id=str(token.id),
        name=token.name,
        description=token.description,
        masked_value=token_manager.mask_value(token.encrypted_value),
        created_by=token.created_by,
        created_at=token.created_at,
        updated_at=token.updated_at,
    )


@router.post("", response_model=TokenResponse, status_code=201)
async def create_token(body: TokenCreate, user: dict = Depends(get_current_user)):
    try:
        token = await token_manager.create_token(
            name=body.name,
            value=body.value,
            description=body.description,
            created_by=user["login"],
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _to_response(token)


@router.get("", response_model=list[TokenResponse])
async def list_tokens(user: dict = Depends(get_current_user)):
    tokens = await token_manager.list_tokens()
    return [_to_response(t) for t in tokens]


@router.get("/{token_id}", response_model=TokenResponse)
async def get_token(token_id: str, user: dict = Depends(get_current_user)):
    token = await Token.get(PydanticObjectId(token_id))
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return _to_response(token)


@router.put("/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: str,
    body: TokenUpdate,
    user: dict = Depends(get_current_user),
):
    token = await Token.get(PydanticObjectId(token_id))
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    token = await token_manager.update_token(
        token, value=body.value, description=body.description
    )
    return _to_response(token)


@router.delete("/{token_id}", status_code=204)
async def delete_token(token_id: str, user: dict = Depends(get_current_user)):
    token = await Token.get(PydanticObjectId(token_id))
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    await token_manager.delete_token(token)
