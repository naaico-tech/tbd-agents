"""CustomTool — user-supplied Python tool stored in MongoDB."""

from datetime import UTC, datetime

from beanie import Document
from pydantic import Field


class CustomTool(Document):
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
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name = "custom_tools"
