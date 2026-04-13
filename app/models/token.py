from datetime import UTC, datetime

from beanie import Document, Indexed
from pydantic import Field


class Token(Document):
    name: Indexed(str, unique=True)
    encrypted_value: str
    description: str = ""
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "tokens"
