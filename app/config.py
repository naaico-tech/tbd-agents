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
    # Short-Term Memory: max recent memories per agent cached in Redis
    stm_max_entries: int = 20
    # Long-Term Memory: max memories per agent stored in MongoDB (0 = unlimited)
    ltm_max_entries: int = 200
    # Prompt context budgets (approximate character budgets before model tokenization)
    prompt_context_char_budget: int = 24000
    prompt_skills_char_budget: int = 6000
    prompt_knowledge_char_budget: int = 12000
    prompt_memory_char_budget: int = 4000
    prompt_context_item_char_limit: int = 1200
    prompt_context_max_items: int = 12
    # Embeddings (fastembed, for semantic memory + knowledge retrieval)
    embeddings_enabled: bool = True
    embeddings_model: str = "BAAI/bge-small-en-v1.5"
    embeddings_dim: int = 384  # auto-detected from model, but used for Qdrant collection creation
    memory_retrieval_top_k: int = 8
    knowledge_retrieval_top_k: int = 8
    knowledge_chunk_chars: int = 1200
    knowledge_chunk_overlap_chars: int = 150
    # Qdrant vector database (required for semantic memory + knowledge retrieval)
    # Set QDRANT_URL to enable; semantic features silently degrade without it.
    qdrant_url: str | None = None
    qdrant_api_key: str | None = None
    # Vector store backend selection
    vector_store_backend: str = "qdrant"  # "qdrant" | "pgvector"
    # PgVector settings (used when vector_store_backend = "pgvector")
    pgvector_dsn: str | None = None  # e.g. postgresql+asyncpg://user:pass@localhost:5432/dbname
    pgvector_table_prefix: str = "vs"  # table name prefix for vector collections
    # Conversation compaction
    compaction_enabled: bool = True
    compaction_token_threshold_pct: float = 0.75  # compact at 75% of context window
    compaction_keep_recent_turns: int = 6
    compaction_summary_max_chars: int = 1500
    tool_result_clearing_enabled: bool = True
    tool_result_clearing_keep_recent: int = 4
    tool_result_context_max_chars: int = 4000
    tool_definition_description_max_chars: int = 240
    # Fernet encryption key for token store
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str | None = None
    # OpenTelemetry
    otel_endpoint: str = "http://otel-collector:4317"
    otel_http_endpoint: str = "http://otel-collector:4318"
    otel_service_name: str = "tbd-agents"
    # Internal API base URL (used by memory MCP server subprocess)
    api_base_url: str = "http://app:8000"
    # Plugin system
    plugins_dir: str = "app/plugins"
    plugins_config: str = "app/plugins.yaml"
    # Max output tokens for Anthropic gateway (messages API) path;
    # adjust for models with lower limits
    anthropic_gateway_max_tokens: int = 8192

    # Database backend
    db_backend: str = "mongo"  # "mongo" or "postgres"
    postgres_uri: str = "postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents"
    postgres_db_name: str = "tbd_agents"

    # ── CodeGraph integration ────────────────────────────────────────────────────
    codegraph_enabled: bool = False
    # URL of the codegraph sidecar container (manages cloning, indexing, and MCP SSE)
    codegraph_sidecar_url: str = "http://codegraph-sidecar:3001"
    # Git clone depth forwarded to the sidecar (1 = shallow, 0 = full history)
    codegraph_clone_depth: int = 1

    model_config = {"env_prefix": "", "env_file": ".env", "extra": "ignore"}


settings = Settings()
