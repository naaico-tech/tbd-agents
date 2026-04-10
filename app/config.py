from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://mongodb:27017"
    mongo_db_name: str = "copilot_agent_hub"
    default_model: str = "gpt-4.1"
    default_max_turns: int = 5
    # Optional server-level GitHub token (per-request tokens take priority)
    github_token: str | None = None
    # Session timeout in seconds
    session_timeout: int = 300
    # Notion integration token for MCP auto-injection
    notion_token: str | None = None
    # Slack bot token for MCP auto-injection
    slack_bot_token: str | None = None

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
