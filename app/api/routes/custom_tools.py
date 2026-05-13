"""CRUD + utility endpoints for Custom Tools.

Routes
------
POST   /api/custom-tools                    Create a custom tool
GET    /api/custom-tools                    List all custom tools
GET    /api/custom-tools/{id}              Get a single tool
PUT    /api/custom-tools/{id}              Update a tool
DELETE /api/custom-tools/{id}              Delete a tool
POST   /api/custom-tools/{id}/run          Ad-hoc test run
POST   /api/custom-tools/validate          Validate source without saving
POST   /api/custom-tools/upload            Upload a .py file
"""

import re as _re
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_current_user
from app.db import parse_doc_id
from app.models.custom_tool import CustomTool
from app.schemas.custom_tool import (
    CustomToolCreate,
    CustomToolResponse,
    CustomToolRunRequest,
    CustomToolRunResponse,
    CustomToolUpdate,
    CustomToolValidateRequest,
    CustomToolValidateResponse,
    EnvMappingResponse,
    EnvMappingUpdate,
    EnvVarEntry,
    TokenRef,
)
from app.services import custom_tool_runner
from app.services import token_manager as _token_manager

router = APIRouter(prefix="/api/custom-tools", tags=["custom tools"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _to_response(tool: CustomTool) -> CustomToolResponse:
    return CustomToolResponse(
        id=str(tool.id),
        name=tool.name,
        description=tool.description,
        source_code=tool.source_code,
        parameters_schema=tool.parameters_schema,
        env_config=tool.env_config,
        tags=tool.tags,
        is_enabled=tool.is_enabled,
        is_plugin=tool.is_plugin,
        created_at=tool.created_at,
        updated_at=tool.updated_at,
    )


async def _get_tool_or_404(tool_id: str) -> CustomTool:
    tool = await CustomTool.get(parse_doc_id(tool_id))
    if not tool:
        raise HTTPException(status_code=404, detail="Custom tool not found")
    return tool


# ── CRUD ─────────────────────────────────────────────────────────────────────


@router.post("", response_model=CustomToolResponse, status_code=201)
async def create_custom_tool(body: CustomToolCreate, _user=Depends(get_current_user)):
    """Create a new custom tool.

    If ``parameters_schema`` is omitted or empty, the runner will attempt to
    infer it from the function signature automatically.
    """
    # Validate source before persisting
    validation = await custom_tool_runner.validate_tool(body.source_code, body.name)
    if not validation.get("valid"):
        raise HTTPException(
            status_code=422,
            detail=f"Source validation failed: {validation.get('error', 'unknown error')}",
        )

    # Auto-infer schema if not supplied
    schema = body.parameters_schema
    if not schema:
        schema = await custom_tool_runner.infer_schema(body.source_code, body.name)

    tool = CustomTool(
        name=body.name,
        description=body.description,
        source_code=body.source_code,
        parameters_schema=schema,
        env_config=body.env_config,
        tags=body.tags,
        is_enabled=body.is_enabled,
    )
    await tool.insert()
    return _to_response(tool)


@router.get("", response_model=list[CustomToolResponse])
async def list_custom_tools(_user=Depends(get_current_user)):
    tools = await CustomTool.find_all().to_list()
    return [_to_response(t) for t in tools]


@router.get("/{tool_id}", response_model=CustomToolResponse)
async def get_custom_tool(tool_id: str, _user=Depends(get_current_user)):
    return _to_response(await _get_tool_or_404(tool_id))


@router.put("/{tool_id}", response_model=CustomToolResponse)
async def update_custom_tool(
    tool_id: str, body: CustomToolUpdate, _user=Depends(get_current_user)
):
    tool = await _get_tool_or_404(tool_id)

    # If source_code or name changed, re-validate and re-infer schema
    new_source = body.source_code if body.source_code is not None else tool.source_code
    new_name = body.name if body.name is not None else tool.name

    if body.source_code is not None or body.name is not None:
        validation = await custom_tool_runner.validate_tool(new_source, new_name)
        if not validation.get("valid"):
            raise HTTPException(
                status_code=422,
                detail=f"Source validation failed: {validation.get('error', 'unknown error')}",
            )
        # Re-infer schema unless explicitly provided
        if body.parameters_schema is None:
            body_dict = body.model_dump(exclude_none=True)
            body_dict["parameters_schema"] = await custom_tool_runner.infer_schema(
                new_source, new_name
            )
            update_data = body_dict
        else:
            update_data = body.model_dump(exclude_none=True)
    else:
        update_data = body.model_dump(exclude_none=True)

    if update_data:
        update_data["updated_at"] = datetime.now(UTC)
        await tool.set(update_data)

    return _to_response(await _get_tool_or_404(tool_id))


@router.get("/{tool_id}/env-mapping", response_model=EnvMappingResponse)
async def get_env_mapping(tool_id: str, _user=Depends(get_current_user)):
    """Return the env-var → token mapping for a tool, plus all available tokens.

    For each entry in env_config, extract the token name from ``{{token:NAME}}``
    references. The ``available_tokens`` list lets clients present a dropdown.
    """
    tool = await _get_tool_or_404(tool_id)

    _TOKEN_REF_RE = _re.compile(r"\{\{token:([^}]+)\}\}")

    env_vars: list[EnvVarEntry] = []
    for env_var, template in tool.env_config.items():
        stripped = template.strip() if template else ""
        match = _TOKEN_REF_RE.fullmatch(stripped) if stripped else None
        current_token = match.group(1) if match else None
        env_vars.append(EnvVarEntry(
            env_var=env_var,
            current_token=current_token,
            template=template,
        ))

    tokens = await _token_manager.list_tokens()
    available = [
        TokenRef(
            id=str(t.id),
            name=t.name,
            description=t.description,
            masked_value=_token_manager.mask_value(t.encrypted_value),
        )
        for t in tokens
    ]

    return EnvMappingResponse(
        tool_id=str(tool.id),
        tool_name=tool.name,
        env_vars=env_vars,
        available_tokens=available,
    )


@router.put("/{tool_id}/env-mapping", response_model=EnvMappingResponse)
async def update_env_mapping(
    tool_id: str,
    body: EnvMappingUpdate,
    _user=Depends(get_current_user),
):
    """Update which token is mapped to each env var in the tool's env_config.

    Only env vars already declared in env_config can be mapped. Attempting to
    map an env var that doesn't exist on the tool raises HTTP 422.
    Unknown token names (tokens that don't exist in the store) are accepted but
    will produce a warning at runtime — this allows pre-configuring a mapping
    before the token is created.

    An empty string value removes the ``{{token:}}`` reference and stores ``""``
    for that env var.
    """
    tool = await _get_tool_or_404(tool_id)

    # Validate: only allow updating env vars already in the tool's env_config
    unknown_vars = set(body.env_var_mapping.keys()) - set(tool.env_config.keys())
    if unknown_vars:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown env vars for this tool: {sorted(unknown_vars)}. "
                   f"Known env vars: {sorted(tool.env_config.keys())}",
        )

    # Build the new env_config: update only the vars present in the request
    new_env_config = dict(tool.env_config)
    for env_var, token_name in body.env_var_mapping.items():
        if token_name:
            new_env_config[env_var] = f"{{{{token:{token_name}}}}}"
        else:
            new_env_config[env_var] = ""

    tool.env_config = new_env_config
    tool.updated_at = datetime.now(UTC)
    await tool.save()

    # Return the updated mapping view (reuse GET logic)
    return await get_env_mapping(tool_id, _user)


@router.delete("/{tool_id}", status_code=204)
async def delete_custom_tool(tool_id: str, _user=Depends(get_current_user)):
    tool = await _get_tool_or_404(tool_id)
    await tool.delete()


# ── Utility endpoints ─────────────────────────────────────────────────────────


@router.post("/{tool_id}/run", response_model=CustomToolRunResponse)
async def run_custom_tool(
    tool_id: str, body: CustomToolRunRequest, _user=Depends(get_current_user)
):
    """Ad-hoc test run of a custom tool with the given arguments."""
    tool = await _get_tool_or_404(tool_id)
    if not tool.is_enabled:
        raise HTTPException(status_code=409, detail="Custom tool is disabled")

    result = await custom_tool_runner.run_tool(tool.source_code, tool.name, body.arguments)

    import json as _json
    try:
        parsed = _json.loads(result)
        success = "error" not in parsed
        error = parsed.get("error") if not success else None
    except Exception:
        success = True
        error = None

    return CustomToolRunResponse(
        tool_name=tool.name,
        result=result,
        success=success,
        error=error,
    )


@router.post("/validate", response_model=CustomToolValidateResponse)
async def validate_custom_tool(
    body: CustomToolValidateRequest, _user=Depends(get_current_user)
):
    """Validate tool source code and return the inferred parameter schema."""
    result = await custom_tool_runner.validate_tool(body.source_code, body.name)
    return CustomToolValidateResponse(
        valid=result.get("valid", False),
        inferred_schema=result.get("inferred_schema"),
        error=result.get("error"),
    )


@router.post("/upload", response_model=CustomToolResponse, status_code=201)
async def upload_custom_tool(
    file: UploadFile = File(...),
    _user=Depends(get_current_user),
):
    """Upload a ``.py`` file and register it as a custom tool.

    The tool name is derived from the filename (stem), e.g. ``my_tool.py``
    → ``my_tool``.  The uploaded file must define a function with that name.
    """
    if not (file.filename or "").endswith(".py"):
        raise HTTPException(status_code=400, detail="Only .py files are accepted")

    from pathlib import Path
    func_name = Path(file.filename).stem

    raw = await file.read()
    source_code = raw.decode("utf-8")

    # Validate
    validation = await custom_tool_runner.validate_tool(source_code, func_name)
    if not validation.get("valid"):
        raise HTTPException(
            status_code=422,
            detail=f"Source validation failed: {validation.get('error', 'unknown error')}",
        )

    schema = validation.get("inferred_schema") or await custom_tool_runner.infer_schema(
        source_code, func_name
    )

    tool = CustomTool(
        name=func_name,
        description=f"Uploaded from {file.filename}",
        source_code=source_code,
        parameters_schema=schema,
    )
    await tool.insert()
    return _to_response(tool)
