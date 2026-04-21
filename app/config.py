from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db_name: str = "copilot_agent_hub"
    default_model: str = "gpt-4.1"
    default_max_turns: int = 5
    # Optional server-level GitHub token (per-request tokens take priority)
    github_token: str | None = None
    # Session timeout in seconds
    session_timeout: int = 600
    # Redis URL for Celery broker/backend and event bus pub/sub
    redis_url: str = "redis://redis:6379/0"
    # Task status event queue retention in seconds (1-3600, capped at one hour)
    task_status_event_ttl_seconds: int = Field(default=3600, ge=1, le=3600)
    # Short-Term Memory: max recent memories per agent cached in Redis
    stm_max_entries: int = 20
    # Long-Term Memory: max memories per agent stored in MongoDB (0 = unlimited)
    ltm_max_entries: int = 200
    # Fernet encryption key for token store.
    # Generate with:
    # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str | None = None
    # OpenTelemetry
    otel_endpoint: str = "http://otel-collector:4317"
    otel_http_endpoint: str = "http://otel-collector:4318"
    otel_service_name: str = "tbd-agents"
    # Internal API base URL (used by memory MCP server subprocess)
    api_base_url: str = "http://app:8000"

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
