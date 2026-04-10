from datetime import datetime

from pydantic import BaseModel


class TokenCreate(BaseModel):
    name: str
    value: str
    description: str = ""


class TokenUpdate(BaseModel):
    value: str | None = None
    description: str | None = None


class TokenResponse(BaseModel):
    id: str
    name: str
    description: str
    masked_value: str
    created_by: str
    created_at: datetime
    updated_at: datetime
