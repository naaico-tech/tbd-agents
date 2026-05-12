import ipaddress
import socket
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

# Private/loopback ranges blocked to prevent SSRF
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # link-local / metadata
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_webhook_url(v: str | None) -> str | None:
    if v is None:
        return v
    parsed = urlparse(v)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Webhook URL must use http or https scheme")
    host = parsed.hostname or ""
    if not host:
        raise ValueError("Webhook URL must contain a valid host")
    # Block metadata endpoint by hostname
    if host in ("metadata.google.internal", "169.254.169.254"):
        raise ValueError("Webhook URL targets a disallowed host")
    # Resolve hostname and check for private/loopback addresses
    try:
        addrs = {info[4][0] for info in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        addrs = set()
    for addr_str in addrs:
        try:
            addr = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if any(addr in net for net in _BLOCKED_NETWORKS):
            raise ValueError("Webhook URL targets a private or reserved IP address")
    return v


class UsageStatsResponse(BaseModel):
    total_premium_requests: float = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cache_read_tokens: int = 0
    total_cache_write_tokens: int = 0
    total_cost: float = 0.0


class WorkflowCreate(BaseModel):
    title: str | None = None
    agent_id: str
    max_turns: int | None = None
    output_format: str = "json"  # json | markdown
    model: str | None = None
    skill_ids: list[str] = []
    skill_tags: list[str] = []  # Tag-based skill selection (union)
    infinite_session: bool = True
    caveman: bool = False
    bypass_memory: bool = False  # Skip memory injection during task runs
    auto_memory: bool = False  # Auto-extract memories after task completion
    tsv_tool_results: bool = False
    reasoning_effort: str | None = None  # low | medium | high
    guardrail_ids: list[str] = []  # Explicitly selected guardrail IDs
    guardrail_tags: list[str] = []  # Tag-based guardrail selection
    repo_url: str | None = None  # GitHub repo URL
    repo_branch: str | None = None  # Branch to checkout
    repo_token_name: str | None = None  # Token Store key for private repos
    credential_overrides: dict[str, str] = {}  # env_var → token_name overrides for custom tools
    webhook_url: str | None = None  # URL to POST to after task completion

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url(v)

    error_webhook_url: str | None = None  # URL to POST to on task failure

    @field_validator("error_webhook_url")
    @classmethod
    def _check_error_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url(v)


class WorkflowUpdate(BaseModel):
    title: str | None = None
    agent_id: str | None = None
    max_turns: int | None = None
    output_format: str | None = None
    model: str | None = None
    skill_ids: list[str] | None = None
    skill_tags: list[str] | None = None  # Tag-based skill selection (union)
    infinite_session: bool | None = None
    caveman: bool | None = None
    bypass_memory: bool | None = None
    auto_memory: bool | None = None
    tsv_tool_results: bool | None = None
    reasoning_effort: str | None = None
    guardrail_ids: list[str] | None = None
    guardrail_tags: list[str] | None = None
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_token_name: str | None = None
    credential_overrides: dict[str, str] | None = None  # env_var → token_name overrides for custom tools
    webhook_url: str | None = None  # URL to POST to after task completion
    error_webhook_url: str | None = None  # URL to POST to on task failure
    status: str | None = None  # active | inactive

    @field_validator("webhook_url")
    @classmethod
    def _check_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url(v)

    @field_validator("error_webhook_url")
    @classmethod
    def _check_error_webhook_url(cls, v: str | None) -> str | None:
        return _validate_webhook_url(v)


class PromptRequest(BaseModel):
    prompt: str | None = None
    request: dict | None = None  # Structured request object for request-guardrail workflows
    reasoning_effort: str | None = None  # Override workflow default at prompt time


class MessageResponse(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    name: str | None = None


class LogEntryResponse(BaseModel):
    timestamp: datetime
    event: str
    detail: str


class PromptResponse(BaseModel):
    workflow_id: str
    task_id: str | None = None
    status: str
    current_turn: int
    max_turns: int
    response: str | None = None
    output_format: str
    infinite_session: bool = True
    caveman: bool = False
    tsv_tool_results: bool = False
    usage: UsageStatsResponse | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse] = []


class WorkflowResponse(BaseModel):
    id: str
    title: str | None = None
    agent_id: str
    github_user: str
    model: str
    max_turns: int
    current_turn: int
    session_id: str | None = None
    skill_ids: list[str]
    skill_tags: list[str] = []
    status: str
    output_format: str
    infinite_session: bool = True
    caveman: bool = False
    bypass_memory: bool = False
    auto_memory: bool = False
    tsv_tool_results: bool = False
    reasoning_effort: str | None = None
    guardrail_ids: list[str] = []
    guardrail_tags: list[str] = []
    repo_url: str | None = None
    repo_branch: str | None = None
    repo_token_name: str | None = None
    credential_overrides: dict[str, str] = {}  # env_var → token_name overrides for custom tools
    webhook_url: str | None = None  # URL to POST to after task completion
    error_webhook_url: str | None = None  # URL to POST to on task failure
    usage: UsageStatsResponse | None = None
    logs: list[LogEntryResponse] = []
    messages: list[MessageResponse]
    task_count: int = 0
    last_task_status: str | None = None
    last_task_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
