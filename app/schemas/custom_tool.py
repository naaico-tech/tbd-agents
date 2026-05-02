"""Pydantic schemas for the Custom Tools API."""

from datetime import datetime

from pydantic import BaseModel


class CustomToolCreate(BaseModel):
    name: str
    description: str = ""
    source_code: str
    parameters_schema: dict = {}
    env_config: dict[str, str] = {}
    tags: list[str] = []
    is_enabled: bool = True


class CustomToolUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_code: str | None = None
    parameters_schema: dict | None = None
    env_config: dict[str, str] | None = None
    tags: list[str] | None = None
    is_enabled: bool | None = None


class CustomToolResponse(BaseModel):
    id: str
    name: str
    description: str
    source_code: str
    parameters_schema: dict
    env_config: dict[str, str]
    tags: list[str]
    is_enabled: bool
    is_plugin: bool
    created_at: datetime
    updated_at: datetime


class CustomToolRunRequest(BaseModel):
    arguments: dict = {}


class CustomToolRunResponse(BaseModel):
    tool_name: str
    result: str
    success: bool
    error: str | None = None


class CustomToolValidateRequest(BaseModel):
    source_code: str
    name: str


class CustomToolValidateResponse(BaseModel):
    valid: bool
    inferred_schema: dict | None = None
    error: str | None = None


class EnvVarEntry(BaseModel):
    """A single env var and its current token assignment."""

    env_var: str
    current_token: str | None  # None if not yet mapped or uses raw value
    template: str  # the raw {{token:name}} or plain value stored in env_config


class TokenRef(BaseModel):
    """A lightweight token reference for mapping dropdowns."""

    id: str
    name: str
    description: str
    masked_value: str


class EnvMappingResponse(BaseModel):
    """Response for GET /api/custom-tools/{id}/env-mapping."""

    tool_id: str
    tool_name: str
    env_vars: list[EnvVarEntry]
    available_tokens: list[TokenRef]


class EnvMappingUpdate(BaseModel):
    """Body for PUT /api/custom-tools/{id}/env-mapping.

    Keys are env var names; values are token names (without the {{token:}} wrapper).
    Set a value to empty string "" to remove the token mapping (keeps env var with empty template).
    """

    env_var_mapping: dict[str, str]
