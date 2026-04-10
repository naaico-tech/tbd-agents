from datetime import datetime

from pydantic import BaseModel


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    instructions: str
    tags: list[str] = []


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    instructions: str | None = None
    tags: list[str] | None = None


class SkillResponse(BaseModel):
    id: str
    name: str
    description: str
    instructions: str
    tags: list[str]
    created_at: datetime
    updated_at: datetime
