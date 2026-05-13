from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.guardrail import (
    Guardrail,
    OutputGuardrailConfig,
    PromptGuardrailConfig,
    RequestGuardrailConfig,
)
from app.schemas.guardrail import GuardrailCreate, GuardrailResponse, GuardrailUpdate

router = APIRouter(prefix="/api/guardrails", tags=["guardrails"])


def _to_response(g: Guardrail) -> GuardrailResponse:
    return GuardrailResponse(
        id=str(g.id),
        name=g.name,
        description=g.description,
        guardrail_type=g.guardrail_type,
        tags=g.tags,
        enabled=g.enabled,
        prompt_config=g.prompt_config.model_dump() if g.prompt_config else None,
        request_config=g.request_config.model_dump() if g.request_config else None,
        output_config=g.output_config.model_dump() if g.output_config else None,
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


@router.post("", response_model=GuardrailResponse, status_code=201)
async def create_guardrail(body: GuardrailCreate, _user=Depends(get_current_user)):
    prompt_cfg = (
        PromptGuardrailConfig(**body.prompt_config.model_dump()) if body.prompt_config else None
    )
    request_cfg = (
        RequestGuardrailConfig(**body.request_config.model_dump()) if body.request_config else None
    )
    output_cfg = (
        OutputGuardrailConfig(**body.output_config.model_dump()) if body.output_config else None
    )
    guardrail = Guardrail(
        name=body.name,
        description=body.description,
        guardrail_type=body.guardrail_type,
        tags=body.tags,
        enabled=body.enabled,
        prompt_config=prompt_cfg,
        request_config=request_cfg,
        output_config=output_cfg,
    )
    await guardrail.insert()
    return _to_response(guardrail)


@router.get("", response_model=list[GuardrailResponse])
async def list_guardrails(
    tag: str | None = None,
    _user=Depends(get_current_user),
):
    """List all guardrails, optionally filtered by a single tag."""
    if tag:
        guardrails = await Guardrail.find({"tags": tag}).to_list()
    else:
        guardrails = await Guardrail.find_all().to_list()
    return [_to_response(g) for g in guardrails]


@router.get("/{guardrail_id}", response_model=GuardrailResponse)
async def get_guardrail(guardrail_id: str, _user=Depends(get_current_user)):
    g = await Guardrail.get(parse_doc_id(guardrail_id))
    if not g:
        raise HTTPException(status_code=404, detail="Guardrail not found")
    return _to_response(g)


@router.put("/{guardrail_id}", response_model=GuardrailResponse)
async def update_guardrail(
    guardrail_id: str, body: GuardrailUpdate, _user=Depends(get_current_user)
):
    g = await Guardrail.get(parse_doc_id(guardrail_id))
    if not g:
        raise HTTPException(status_code=404, detail="Guardrail not found")

    updates = body.model_dump(exclude_unset=True)

    if "prompt_config" in updates:
        pc = updates.pop("prompt_config")
        g.prompt_config = PromptGuardrailConfig(**pc) if pc else None

    if "request_config" in updates:
        rc = updates.pop("request_config")
        g.request_config = RequestGuardrailConfig(**rc) if rc else None

    if "output_config" in updates:
        oc = updates.pop("output_config")
        g.output_config = OutputGuardrailConfig(**oc) if oc else None

    for k, v in updates.items():
        setattr(g, k, v)

    g.updated_at = datetime.now(UTC)
    await g.save()
    return _to_response(g)


@router.delete("/{guardrail_id}", status_code=204)
async def delete_guardrail(guardrail_id: str, _user=Depends(get_current_user)):
    g = await Guardrail.get(parse_doc_id(guardrail_id))
    if not g:
        raise HTTPException(status_code=404, detail="Guardrail not found")
    await g.delete()
    return None
