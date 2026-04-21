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
