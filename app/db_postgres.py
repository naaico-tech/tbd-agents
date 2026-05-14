"""PostgreSQL async backend using SQLAlchemy 2.0 + structured typed columns."""
from __future__ import annotations

import json
import re
import types as _builtin_types
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel
from sqlalchemy import BOOLEAN, DOUBLE_PRECISION, INTEGER, TEXT, TIMESTAMP, bindparam, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# Convenience alias — TIMESTAMPTZ is TIMESTAMP(timezone=True) in SQLAlchemy
TIMESTAMPTZ = TIMESTAMP(timezone=True)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Safe SQL identifier pattern — prevents ORDER BY injection
_SAFE_IDENT = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# All 15 MongoDB collection names that need PostgreSQL tables
COLLECTIONS = [
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

# ---------------------------------------------------------------------------
# Per-table structured DDL — no generic JSONB data blob
# ---------------------------------------------------------------------------

_TABLE_DDL: dict[str, str] = {
    "agents": """
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
        )""",
    "chat_sessions": """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            agent_id TEXT NOT NULL,
            github_user TEXT NOT NULL,
            title TEXT,
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
    "chat_messages": """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            usage JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
    "memories": """
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
        )""",
    "skills": """
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            instructions TEXT NOT NULL DEFAULT '',
            tags TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
    "tokens": """
        CREATE TABLE IF NOT EXISTS tokens (
            id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name TEXT NOT NULL UNIQUE,
            encrypted_value TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            created_by TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
    "providers": """
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
        )""",
    "knowledge_items": """
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
        )""",
    "knowledge_sources": """
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
        )""",
    "custom_tools": """
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
        )""",
    "guardrails": """
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
        )""",
    "workflows": """
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
        )""",
    "task_executions": """
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
        )""",
    "scheduled_agents": """
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
        )""",
    "mcp_servers": """
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
        )""",
}

_INDEX_DDL: dict[str, str] = {
    "chat_sessions": (
        "CREATE INDEX IF NOT EXISTS idx_chat_sessions_agent_id ON chat_sessions (agent_id)"
    ),
    "chat_messages": (
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (session_id)"
    ),
    "memories": (
        "CREATE INDEX IF NOT EXISTS idx_memories_agent_id ON memories (agent_id)"
    ),
    "workflows": (
        "CREATE INDEX IF NOT EXISTS idx_workflows_agent_id ON workflows (agent_id)"
    ),
    "task_executions": (
        "CREATE INDEX IF NOT EXISTS idx_task_executions_workflow_id"
        " ON task_executions (workflow_id)"
    ),
    "knowledge_items": (
        "CREATE INDEX IF NOT EXISTS idx_knowledge_items_source_id"
        " ON knowledge_items (source_id)"
    ),
}

# Global document registry populated by PostgresDocument.__init_subclass__
_DOC_REGISTRY: dict[str, type] = {}


# ---------------------------------------------------------------------------
# Type mapping helpers
# ---------------------------------------------------------------------------


def _python_to_sa_type(annotation: Any) -> Any:
    """Map a Python type annotation to a SQLAlchemy type object."""
    origin = get_origin(annotation)
    args = get_args(annotation)

    # Unwrap Optional[X] — handles both typing.Union[X, None] and Python 3.10+ X | None
    _is_union = origin is Union or isinstance(annotation, _builtin_types.UnionType)
    if _is_union and type(None) in args:
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _python_to_sa_type(non_none[0])

    if annotation is str:
        return TEXT()
    if annotation is int:
        return INTEGER()
    if annotation is float:
        return DOUBLE_PRECISION()
    if annotation is bool:
        return BOOLEAN()
    if annotation is datetime:
        return TIMESTAMPTZ
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return TEXT()

    # Bare list / dict without type parameters
    if annotation is list or annotation is dict:
        return JSONB()

    if origin is list and args:
        inner = args[0]
        if inner is str:
            return ARRAY(TEXT())
        if inner is int:
            return ARRAY(INTEGER())
        if inner is float:
            return ARRAY(DOUBLE_PRECISION())
        # list[dict], list[BaseModel], etc.
        return JSONB()

    if origin is dict:
        return JSONB()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return JSONB()

    # fallback
    return TEXT()


def _serialize_value(value: Any, sa_type: Any) -> Any:
    """Serialize a Python value for binding against *sa_type*."""
    if value is None:
        return None
    if isinstance(sa_type, JSONB):
        if isinstance(value, BaseModel):
            return value.model_dump(mode="json")
        if isinstance(value, list):
            return [
                v.model_dump(mode="json") if isinstance(v, BaseModel) else v for v in value
            ]
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [v.value if isinstance(v, Enum) else v for v in value]
    return value


# ---------------------------------------------------------------------------
# Engine / session factory
# ---------------------------------------------------------------------------


async def get_engine() -> AsyncEngine:
    """Return (or create) the shared async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.postgres_uri,
            echo=False,
            pool_pre_ping=True,
            json_serializer=lambda obj: json.dumps(obj, default=str),
        )
    return _engine


async def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return (or create) the shared async session factory."""
    global _session_factory
    if _session_factory is None:
        engine = await get_engine()
        _session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return _session_factory


async def init_postgres() -> None:
    """Create all tables and indexes if they don't exist."""
    engine = await get_engine()
    async with engine.begin() as conn:
        try:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "pgcrypto"'))
        except ProgrammingError as e:
            if "already exists" not in str(e).lower():
                raise
        for collection, ddl in _TABLE_DDL.items():
            await conn.execute(text(ddl))
            idx_sql = _INDEX_DDL.get(collection, "")
            if idx_sql:
                await conn.execute(text(idx_sql))


async def close_postgres() -> None:
    """Dispose the engine and reset module-level singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# ---------------------------------------------------------------------------
# Filter translator — direct column references (no data->>'field' JSONB paths)
# ---------------------------------------------------------------------------


def _translate_filters(
    model_cls: type,
    filters: dict[str, Any],
    params: dict,
) -> str:
    """Translate a MongoDB-style filter dict to a structured-column WHERE clause.

    Supported operators: $in, $ne, $lt, $gt, $lte, $gte, $exists.
    Returns a SQL string with named bind parameters written into *params*.

    Args:
        model_cls: The PostgresDocument subclass (used to resolve SA column types).
        filters:   MongoDB-style filter dict.
        params:    Mutable dict that receives the bind-parameter values.
    """
    conditions: list[str] = []
    param_idx = len(params)
    col_map: dict[str, Any] = (
        model_cls._get_column_map()  # type: ignore[attr-defined]
        if hasattr(model_cls, "_get_column_map")
        else {}
    )

    for key, value in filters.items():
        col_key = "id" if key in ("_id", "id") else key
        sa_type = col_map.get(col_key, TEXT())

        if isinstance(value, dict):
            for op, op_val in value.items():
                param_name = f"p{param_idx}"
                param_idx += 1

                if op == "$in":
                    if not op_val:
                        conditions.append("FALSE")
                    else:
                        phs: list[str] = []
                        for v in op_val:
                            pn = f"p{param_idx}"
                            param_idx += 1
                            params[pn] = v.value if isinstance(v, Enum) else v
                            phs.append(f":{pn}")
                        conditions.append(f"{col_key} IN ({', '.join(phs)})")

                elif op == "$ne":
                    params[param_name] = op_val.value if isinstance(op_val, Enum) else op_val
                    conditions.append(f"{col_key} != :{param_name}")

                elif op == "$lt":
                    params[param_name] = op_val
                    conditions.append(f"{col_key} < :{param_name}")

                elif op == "$gt":
                    params[param_name] = op_val
                    conditions.append(f"{col_key} > :{param_name}")

                elif op == "$lte":
                    params[param_name] = op_val
                    conditions.append(f"{col_key} <= :{param_name}")

                elif op == "$gte":
                    params[param_name] = op_val
                    conditions.append(f"{col_key} >= :{param_name}")

                elif op == "$exists":
                    if op_val:
                        conditions.append(f"{col_key} IS NOT NULL")
                    else:
                        conditions.append(f"{col_key} IS NULL")

                # unused param_name slot — advance index to stay consistent
                else:
                    param_idx -= 1  # revert the pre-increment for unused slot

        elif value is None:
            conditions.append(f"{col_key} IS NULL")

        else:
            param_name = f"p{param_idx}"
            param_idx += 1
            params[param_name] = _serialize_value(value, sa_type)
            # For ARRAY columns, a scalar filter means "value is in the array"
            if isinstance(sa_type, ARRAY):
                conditions.append(f":{param_name} = ANY({col_key})")
            else:
                conditions.append(f"{col_key} = :{param_name}")

    return " AND ".join(conditions) if conditions else "TRUE"


# ---------------------------------------------------------------------------
# PgQuerySet — chainable query builder
# ---------------------------------------------------------------------------


@dataclass
class _DeleteResult:
    """Minimal delete-result object that mirrors Beanie's DeleteResult interface."""

    deleted_count: int


class PgQuerySet[T]:  # noqa: UP046 — T bound at call-site via PostgresDocument
    """Chainable query builder that mimics Beanie's FindMany interface."""

    def __init__(self, model_cls: type[T], filters: dict | None = None) -> None:
        self._model_cls = model_cls
        self._filters: dict = filters or {}
        self._sort_fields: list[str] = []
        self._limit_val: int | None = None
        self._skip_val: int = 0

    def sort(self, *fields: str) -> PgQuerySet[T]:
        qs = PgQuerySet(self._model_cls, self._filters)
        qs._sort_fields = list(fields)
        qs._limit_val = self._limit_val
        qs._skip_val = self._skip_val
        return qs

    def limit(self, n: int) -> PgQuerySet[T]:
        qs = PgQuerySet(self._model_cls, self._filters)
        qs._sort_fields = self._sort_fields
        qs._limit_val = n
        qs._skip_val = self._skip_val
        return qs

    def skip(self, n: int) -> PgQuerySet[T]:
        qs = PgQuerySet(self._model_cls, self._filters)
        qs._sort_fields = self._sort_fields
        qs._limit_val = self._limit_val
        qs._skip_val = n
        return qs

    def _build_query(self) -> tuple[str, dict]:
        table = self._model_cls.get_collection_name()
        params: dict = {}
        where = _translate_filters(self._model_cls, self._filters, params)

        sql = f"SELECT * FROM {table} WHERE {where}"

        if self._sort_fields:
            order_parts: list[str] = []
            for f in self._sort_fields:
                if f.startswith(("-", "+")):
                    direction = "DESC" if f.startswith("-") else "ASC"
                    field = f[1:]
                else:
                    direction = "ASC"
                    field = f
                if _SAFE_IDENT.match(field):
                    order_parts.append(f"{field} {direction}")
            sql += f" ORDER BY {', '.join(order_parts)}"
        else:
            sql += " ORDER BY created_at DESC"

        if self._limit_val is not None:
            sql += f" LIMIT {self._limit_val}"
        if self._skip_val:
            sql += f" OFFSET {self._skip_val}"

        return sql, params

    async def to_list(self) -> list[T]:
        sql, params = self._build_query()
        factory = await get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), params)
            # Convert RowMapping objects to plain dicts so _from_row works uniformly
            rows = [dict(row) for row in result.mappings().fetchall()]
        return [self._model_cls._from_row(row) for row in rows]

    async def count(self) -> int:
        table = self._model_cls.get_collection_name()
        params: dict = {}
        where = _translate_filters(self._model_cls, self._filters, params)
        sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
        factory = await get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), params)
            return result.scalar() or 0

    async def delete(self) -> _DeleteResult:
        """Delete all rows matching the current filters and return a result object.

        Mirrors Beanie's ``FindMany.delete()`` — returns a :class:`_DeleteResult`
        with a ``deleted_count`` attribute so callers can do::

            result = await Model.find({...}).delete()
            count  = result.deleted_count
        """
        table = self._model_cls.get_collection_name()
        params: dict = {}
        where = _translate_filters(self._model_cls, self._filters, params)
        sql = f"DELETE FROM {table} WHERE {where}"
        factory = await get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), params)
            await session.commit()
        return _DeleteResult(deleted_count=result.rowcount)

    def __await__(self):
        return self.to_list().__await__()


# ---------------------------------------------------------------------------
# PostgresDocument — drop-in Beanie Document replacement
# ---------------------------------------------------------------------------


class PostgresDocument:
    """Drop-in replacement for Beanie's Document using structured typed columns.

    Subclasses (which are also Pydantic models) define fields normally; the
    class maps each field to the appropriate SQL column type via
    :func:`_python_to_sa_type`.

    Example::

        class Agent(PostgresDocument, BaseModel):
            name: str
            description: str = ""

            class Settings:
                name = "agents"
    """

    class Settings:
        name: str = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        collection = cls.get_collection_name()
        if collection:
            _DOC_REGISTRY[collection] = cls

    @classmethod
    def get_collection_name(cls) -> str:
        return cls.Settings.name

    # ------------------------------------------------------------------
    # Column-map helpers
    # ------------------------------------------------------------------

    @classmethod
    def _get_column_map(cls) -> dict[str, Any]:
        """Return ``{field_name: sa_type}`` for all model fields (excluding *id*)."""
        result: dict[str, Any] = {}
        if not hasattr(cls, "model_fields"):
            return result
        for name, field_info in cls.model_fields.items():
            if name == "id":
                continue
            annotation = field_info.annotation
            result[name] = _python_to_sa_type(annotation)
        return result

    def _to_columns(self) -> dict[str, Any]:
        """Return ``{col_name: serialized_value}`` for all non-id fields."""
        col_map = self.__class__._get_column_map()
        result: dict[str, Any] = {}
        for name, sa_type in col_map.items():
            value = getattr(self, name, None)
            result[name] = _serialize_value(value, sa_type)
        return result

    @classmethod
    def _from_row(cls, row: Any) -> PostgresDocument:
        """Reconstruct a model instance from a structured-column row.

        Accepts plain dicts (preferred — from to_list()), Row objects with
        ``._mapping``, namedtuple-like rows with ``._asdict()``, or the legacy
        ``(id, data_blob, created_at, updated_at)`` tuple format.
        """
        if isinstance(row, dict):
            data = row
        elif hasattr(row, "_mapping"):
            data = dict(row._mapping)
        elif hasattr(row, "_asdict"):
            data = row._asdict()
        else:
            # Legacy fallback: (id, data_blob, created_at, updated_at)
            raw: dict = row[1] if isinstance(row[1], dict) else json.loads(row[1])
            raw["id"] = row[0]
            if len(row) > 2:
                raw["created_at"] = row[2]
            if len(row) > 3:
                raw["updated_at"] = row[3]
            data = raw

        # JSONB fields come back as Python dicts/lists; Enum fields as strings.
        # Pydantic handles coercion on model_validate.
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls(**data)

    # ------------------------------------------------------------------
    # Class-level query helpers (mirrors Beanie Document API)
    # ------------------------------------------------------------------

    @classmethod
    def find_all(cls) -> PgQuerySet:
        return PgQuerySet(cls, {})

    @classmethod
    def find(cls, *conditions: Any, **filters: Any) -> PgQuerySet:
        merged: dict = {}
        for c in conditions:
            if isinstance(c, dict):
                merged.update(c)
        merged.update(filters)
        return PgQuerySet(cls, merged)

    @classmethod
    async def find_one(cls, *conditions: Any, **filters: Any) -> PostgresDocument | None:
        results = await cls.find(*conditions, **filters).limit(1).to_list()
        return results[0] if results else None

    @classmethod
    async def get(cls, doc_id: Any) -> PostgresDocument | None:
        return await cls.find_one({"id": str(doc_id)})

    async def insert(self) -> PostgresDocument:
        """Insert this document as a new row (alias for save())."""
        await self.save()
        return self

    # ------------------------------------------------------------------
    # Instance-level persistence helpers
    # ------------------------------------------------------------------

    async def save(self) -> PostgresDocument:
        """Upsert this document into the database using structured columns."""
        table = self.get_collection_name()
        now = datetime.now(UTC)

        # Resolve or generate the primary key
        doc_id = getattr(self, "id", None)
        if not doc_id:
            doc_id = str(uuid.uuid4())
            object.__setattr__(self, "id", doc_id)
        else:
            doc_id = str(doc_id)

        col_map = self.__class__._get_column_map()
        col_values: dict[str, Any] = {"id": doc_id}

        for name, sa_type in col_map.items():
            if name == "created_at":
                existing = getattr(self, "created_at", None)
                col_values["created_at"] = existing if existing else now
            elif name == "updated_at":
                col_values["updated_at"] = now
                object.__setattr__(self, "updated_at", now)
            else:
                value = getattr(self, name, None)
                col_values[name] = _serialize_value(value, sa_type)

        # Ensure timestamps exist even when the model has no explicit fields for them
        if "created_at" not in col_values:
            col_values["created_at"] = now
        cls = self.__class__
        has_updated_at = "updated_at" in getattr(cls, "model_fields", {})
        if has_updated_at and "updated_at" not in col_values:
            col_values["updated_at"] = now

        all_cols = list(col_values.keys())
        col_list = ", ".join(all_cols)
        param_list = ", ".join(f":{c}" for c in all_cols)
        update_set = ", ".join(
            f"{c} = EXCLUDED.{c}" for c in all_cols if c not in ("id", "created_at")
        )

        sql = text(
            f"INSERT INTO {table} ({col_list}) VALUES ({param_list}) "
            f"ON CONFLICT (id) DO UPDATE SET {update_set}"
        )

        # Annotate JSONB and ARRAY params so SQLAlchemy/asyncpg handles serialization
        # correctly — avoids the :col::jsonb cast that breaks asyncpg positional params.
        bp_list: list[Any] = []
        col_sa_types: dict[str, Any] = {
            "id": TEXT(),
            "created_at": TIMESTAMPTZ,
            "updated_at": TIMESTAMPTZ,
            **col_map,
        }
        for col, sa_type in col_sa_types.items():
            if col in col_values and isinstance(sa_type, (JSONB, ARRAY)):
                bp_list.append(bindparam(col, type_=sa_type))
        if bp_list:
            sql = sql.bindparams(*bp_list)

        factory = await get_session_factory()
        async with factory() as session:
            await session.execute(sql, col_values)
            await session.commit()
        return self

    async def set(self, update_data: dict[str, Any]) -> PostgresDocument:
        """Apply a partial update dict and persist. Compatible with Beanie's Document.set()."""
        for key, value in update_data.items():
            object.__setattr__(self, key, value)
        await self.save()
        return self

    async def delete(self) -> None:
        """Delete this document from the database."""
        table = self.get_collection_name()
        raw_id = getattr(self, "id", None)
        if not raw_id:
            raise ValueError("Cannot delete a document without an id")
        doc_id = str(raw_id)
        factory = await get_session_factory()
        async with factory() as session:
            await session.execute(
                text(f"DELETE FROM {table} WHERE id = :id"),
                {"id": doc_id},
            )
            await session.commit()
