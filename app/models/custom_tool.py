"""CustomTool — user-supplied Python tool stored in MongoDB or PostgreSQL."""

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

else:
    from beanie import Document as _DocumentBase  # type: ignore[assignment]


class CustomTool(_DocumentBase):  # type: ignore[valid-type]
    """A user-supplied Python function exposed as an agent tool.

    ``source_code`` must define a top-level function whose name matches
    ``name``.  The function may be synchronous or ``async``.

    ``parameters_schema`` is a JSON Schema dict describing the function's
    inputs.  If omitted on creation the runner will attempt to infer it
    from the function signature via ``inspect``.
    """

    name: str
    description: str = ""
    source_code: str
    parameters_schema: dict = Field(default_factory=dict)
    env_config: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    is_plugin: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "custom_tools"
