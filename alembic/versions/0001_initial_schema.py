"""Initial schema: create all 15 document collections.

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

# All 15 collection table names (matches COLLECTIONS in app/db_postgres.py)
_COLLECTIONS = [
    "agents",
    "chat_sessions",
    "chat_messages",
    "memories",
    "skills",
    "tokens",
    "providers",
    "knowledge_items",
    "knowledge_sources",
    "custom_tools",
    "guardrails",
    "workflows",
    "task_executions",
    "scheduled_agents",
    "mcp_servers",
]


def upgrade() -> None:
    # Enable pgcrypto for gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Create each collection table + GIN index
    for table in _COLLECTIONS:
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id          TEXT        PRIMARY KEY DEFAULT gen_random_uuid()::text,
                data        JSONB       NOT NULL DEFAULT '{{}}'::jsonb,
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_gin ON {table} USING GIN (data)"
        )

    # vs_collections table used by the pgvector adapter
    op.execute("""
        CREATE TABLE IF NOT EXISTS vs_collections (
            name         TEXT    PRIMARY KEY,
            vector_size  INTEGER NOT NULL,
            distance     TEXT    NOT NULL DEFAULT 'cosine',
            created_at   TIMESTAMPTZ DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    # Drop vs_collections first, then all collection tables
    op.execute("DROP TABLE IF EXISTS vs_collections")

    # Drop in reverse order (no FKs, so order is cosmetic)
    for table in reversed(_COLLECTIONS):
        op.execute(f"DROP TABLE IF EXISTS {table}")

    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
