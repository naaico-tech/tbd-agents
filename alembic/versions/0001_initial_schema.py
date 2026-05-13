"""Initial schema: create all 15 typed tables plus pgvector adapter table.

Revision ID: 0001
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | tuple[str, ...] | None = None
depends_on: str | tuple[str, ...] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT 'You are a helpful assistant.',
            model TEXT,
            mcp_server_ids TEXT[] NOT NULL DEFAULT '{}',
            mcp_server_tags TEXT[] NOT NULL DEFAULT '{}',
            tool_definitions JSONB NOT NULL DEFAULT '[]',
            knowledge_source_ids TEXT[] NOT NULL DEFAULT '{}',
            knowledge_tags TEXT[] NOT NULL DEFAULT '{}',
            builtin_tools TEXT[] NOT NULL DEFAULT '{}',
            custom_tool_ids TEXT[] NOT NULL DEFAULT '{}',
            provider_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            agent_id TEXT NOT NULL,
            github_user TEXT NOT NULL,
            title TEXT,
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent_id ON chat_sessions (agent_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            usage JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id"
        " ON chat_messages (session_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            agent_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            embedding DOUBLE PRECISION[],
            metadata JSONB NOT NULL DEFAULT '{}',
            ttl TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_memories_agent_id ON memories (agent_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            tags TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL UNIQUE,
            encrypted_value TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL UNIQUE,
            provider_type TEXT NOT NULL,
            api_key_token_name TEXT NOT NULL DEFAULT '',
            base_url TEXT,
            auth_type TEXT NOT NULL DEFAULT 'x-api-key',
            azure_api_version TEXT NOT NULL DEFAULT '2024-12-01-preview',
            azure_deployment TEXT,
            description TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_items (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            source_id TEXT NOT NULL,
            name TEXT NOT NULL,
            content_type TEXT NOT NULL,
            text_content TEXT,
            file_id TEXT,
            file_name TEXT,
            file_size INTEGER,
            mime_type TEXT,
            tags TEXT[] NOT NULL DEFAULT '{}',
            metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_knowledge_items_source_id"
        " ON knowledge_items (source_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_sources (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            connection_config JSONB NOT NULL DEFAULT '{}',
            tags TEXT[] NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'REGISTERED',
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS custom_tools (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            source_code TEXT NOT NULL DEFAULT '',
            parameters_schema JSONB NOT NULL DEFAULT '{}',
            env_config JSONB NOT NULL DEFAULT '{}',
            tags TEXT[] NOT NULL DEFAULT '{}',
            is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            is_plugin BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS guardrails (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            guardrail_type TEXT NOT NULL,
            tags TEXT[] NOT NULL DEFAULT '{}',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            prompt_config JSONB,
            request_config JSONB,
            output_config JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            title TEXT,
            agent_id TEXT NOT NULL DEFAULT '',
            github_user TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            max_turns INTEGER NOT NULL DEFAULT 5,
            current_turn INTEGER NOT NULL DEFAULT 0,
            session_id TEXT,
            skill_ids TEXT[] NOT NULL DEFAULT '{}',
            skill_tags TEXT[] NOT NULL DEFAULT '{}',
            messages JSONB NOT NULL DEFAULT '[]',
            logs JSONB NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'ACTIVE',
            output_format TEXT NOT NULL DEFAULT 'JSON',
            usage JSONB,
            infinite_session BOOLEAN NOT NULL DEFAULT TRUE,
            caveman BOOLEAN NOT NULL DEFAULT FALSE,
            bypass_memory BOOLEAN NOT NULL DEFAULT FALSE,
            auto_memory BOOLEAN NOT NULL DEFAULT FALSE,
            tsv_tool_results BOOLEAN NOT NULL DEFAULT FALSE,
            reasoning_effort TEXT,
            guardrail_ids TEXT[] NOT NULL DEFAULT '{}',
            guardrail_tags TEXT[] NOT NULL DEFAULT '{}',
            repo_url TEXT,
            repo_branch TEXT,
            repo_token_name TEXT,
            credential_overrides JSONB NOT NULL DEFAULT '{}',
            webhook_url TEXT,
            error_webhook_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_workflows_agent_id ON workflows (agent_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS task_executions (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            workflow_id TEXT NOT NULL,
            prompt TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PENDING',
            celery_task_id TEXT,
            worker TEXT,
            model TEXT,
            reasoning_effort TEXT,
            tool_calls INTEGER NOT NULL DEFAULT 0,
            response TEXT,
            progress JSONB,
            logs JSONB NOT NULL DEFAULT '[]',
            messages JSONB NOT NULL DEFAULT '[]',
            usage JSONB,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            scheduled_agent_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_task_executions_workflow_id"
        " ON task_executions (workflow_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_agents (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            prompt TEXT NOT NULL DEFAULT '',
            interval_value INTEGER NOT NULL DEFAULT 1,
            interval_unit TEXT NOT NULL DEFAULT 'MINUTES',
            start_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            end_at TIMESTAMPTZ,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_run_at TIMESTAMPTZ,
            next_run_at TIMESTAMPTZ,
            redbeat_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            transport_type TEXT NOT NULL,
            connection_config JSONB NOT NULL DEFAULT '{}',
            allowed_tools TEXT[] NOT NULL DEFAULT '{}',
            tags TEXT[] NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'REGISTERED',
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # pgvector adapter tracking table
    op.execute("""
        CREATE TABLE IF NOT EXISTS vs_collections (
            name TEXT PRIMARY KEY,
            vector_size INTEGER NOT NULL,
            distance TEXT NOT NULL DEFAULT 'cosine',
            created_at TIMESTAMPTZ DEFAULT now()
        )
    """)


def downgrade() -> None:
    tables = [
        "vs_collections", "mcp_servers", "scheduled_agents", "task_executions",
        "workflows", "guardrails", "custom_tools", "knowledge_sources",
        "knowledge_items", "providers", "tokens", "skills", "memories",
        "chat_messages", "chat_sessions", "agents",
    ]
    for t in tables:
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
