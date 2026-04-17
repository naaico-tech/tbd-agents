from datetime import datetime

from pydantic import BaseModel, model_validator

from app.models.guardrail import GuardrailType


class PromptGuardrailConfigCreate(BaseModel):
    forbidden_patterns: list[str] = []
    required_patterns: list[str] = []
    max_length: int | None = None
    min_length: int | None = None


class RequestGuardrailConfigCreate(BaseModel):
    json_schema: dict


class OutputGuardrailConfigCreate(BaseModel):
    forbidden_patterns: list[str] = []
    required_patterns: list[str] = []
    max_length: int | None = None
    pii_detection: bool = False
    must_be_valid_json: bool = False


class GuardrailCreate(BaseModel):
    name: str
    description: str = ""
    guardrail_type: GuardrailType
    tags: list[str] = []
    enabled: bool = True
    prompt_config: PromptGuardrailConfigCreate | None = None
    request_config: RequestGuardrailConfigCreate | None = None
    output_config: OutputGuardrailConfigCreate | None = None

    @model_validator(mode="after")
    def validate_config(self) -> "GuardrailCreate":
        if self.guardrail_type == GuardrailType.PROMPT and self.prompt_config is None:
            raise ValueError("prompt_config is required for guardrail_type='prompt'")
        if self.guardrail_type == GuardrailType.REQUEST and self.request_config is None:
            raise ValueError("request_config is required for guardrail_type='request'")
        if self.guardrail_type == GuardrailType.OUTPUT and self.output_config is None:
            raise ValueError("output_config is required for guardrail_type='output'")
        return self


class GuardrailUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    prompt_config: PromptGuardrailConfigCreate | None = None
    request_config: RequestGuardrailConfigCreate | None = None
    output_config: OutputGuardrailConfigCreate | None = None


class PromptGuardrailConfigResponse(BaseModel):
    forbidden_patterns: list[str]
    required_patterns: list[str]
    max_length: int | None
    min_length: int | None


class RequestGuardrailConfigResponse(BaseModel):
    json_schema: dict


class OutputGuardrailConfigResponse(BaseModel):
    forbidden_patterns: list[str]
    required_patterns: list[str]
    max_length: int | None
    pii_detection: bool
    must_be_valid_json: bool


class GuardrailResponse(BaseModel):
    id: str
    name: str
    description: str
    guardrail_type: GuardrailType
    tags: list[str]
    enabled: bool
    prompt_config: PromptGuardrailConfigResponse | None
    request_config: RequestGuardrailConfigResponse | None
    output_config: OutputGuardrailConfigResponse | None
    created_at: datetime
    updated_at: datetime
