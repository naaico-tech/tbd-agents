from datetime import UTC, datetime
from enum import StrEnum

from beanie import Document
from pydantic import BaseModel, Field, model_validator


class GuardrailType(StrEnum):
    PROMPT = "prompt"
    REQUEST = "request"
    OUTPUT = "output"


class PromptGuardrailConfig(BaseModel):
    """Validation rules applied to the incoming prompt string."""

    forbidden_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that must NOT match the prompt. Violation blocks the request.",
    )
    required_patterns: list[str] = Field(
        default_factory=list,
        description=(
            "Regex patterns that MUST all match the prompt. "
            "Missing match blocks the request."
        ),
    )
    max_length: int | None = Field(
        default=None,
        description="Maximum allowed prompt length in characters.",
    )
    min_length: int | None = Field(
        default=None,
        description="Minimum required prompt length in characters.",
    )


class RequestGuardrailConfig(BaseModel):
    """Validation rules applied to the structured request object."""

    json_schema: dict = Field(
        description="JSON Schema (draft-07) the request object must conform to.",
    )


class OutputGuardrailConfig(BaseModel):
    """Validation rules applied to the agent's response after execution."""

    forbidden_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that must NOT match the output. Violation flags the response.",
    )
    required_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that MUST all match the output.",
    )
    max_length: int | None = Field(
        default=None,
        description="Maximum allowed output length in characters.",
    )
    pii_detection: bool = Field(
        default=False,
        description="Enable basic PII detection (emails, phone numbers, SSNs).",
    )
    must_be_valid_json: bool = Field(
        default=False,
        description="Require the output to be valid JSON.",
    )


class Guardrail(Document):
    name: str
    description: str = ""
    guardrail_type: GuardrailType
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    prompt_config: PromptGuardrailConfig | None = None
    request_config: RequestGuardrailConfig | None = None
    output_config: OutputGuardrailConfig | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_config_matches_type(self) -> "Guardrail":
        if self.guardrail_type == GuardrailType.PROMPT and self.prompt_config is None:
            raise ValueError("prompt_config is required for guardrail_type='prompt'")
        if self.guardrail_type == GuardrailType.REQUEST and self.request_config is None:
            raise ValueError("request_config is required for guardrail_type='request'")
        if self.guardrail_type == GuardrailType.OUTPUT and self.output_config is None:
            raise ValueError("output_config is required for guardrail_type='output'")
        return self

    class Settings:
        name = "guardrails"
