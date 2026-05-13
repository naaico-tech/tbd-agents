import os as _os
from datetime import UTC, datetime

from pydantic import Field

_POSTGRES = _os.environ.get("DB_BACKEND", "mongo").lower() == "postgres"

if _POSTGRES:
    from pydantic import BaseModel as _PyBase
    from pydantic import Field as _PgField

    from app.db_postgres import PostgresDocument as _PgBase

    class _DocumentBase(_PgBase, _PyBase):  # type: ignore[misc]
        id: str | None = _PgField(default=None)

    def _Indexed(t: type, **_kw: object) -> type:  # noqa: N802
        return t

else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]
    from beanie import Indexed as _Indexed  # type: ignore[assignment]


class Token(_DocumentBase):  # type: ignore[valid-type]
    name: _Indexed(str, unique=True)  # type: ignore[valid-type]
    encrypted_value: str
    description: str = ""
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "tokens"
