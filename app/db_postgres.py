"""PostgreSQL async backend using SQLAlchemy 2.0 + JSONB document storage."""
from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

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

# DDL for each table - JSONB document storage pattern
_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS {table} (
    id TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    data JSONB NOT NULL DEFAULT '{{}}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_{table}_gin ON {table} USING gin(data);
"""

# Global document registry populated by PostgresDocument.__init_subclass__
_DOC_REGISTRY: dict[str, type] = {}


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
    """Create all tables (and GIN indexes) if they don't exist."""
    engine = await get_engine()
    async with engine.begin() as conn:
        # Enable uuid-ossp extension for gen_random_uuid() fallback
        try:
            await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
        except Exception:  # noqa: BLE001
            pass
        for collection in COLLECTIONS:
            ddl = _TABLE_DDL.format(table=collection)
            for stmt in ddl.strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    await conn.execute(text(stmt))


async def close_postgres() -> None:
    """Dispose the engine and reset module-level singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


# ---------------------------------------------------------------------------
# JSONB filter translator
# ---------------------------------------------------------------------------


def _translate_filters(filters: dict[str, Any], params: dict) -> str:
    """Translate a MongoDB-style filter dict to a PostgreSQL JSONB WHERE clause.

    Supported operators: $in, $ne, $lt, $gt, $lte, $gte, $exists.
    Returns a SQL string with named bind parameters written into *params*.
    """
    conditions: list[str] = []
    param_idx = len(params)

    for key, value in filters.items():
        if key in ("_id", "id"):
            param_name = f"p{param_idx}"
            params[param_name] = str(value)
            conditions.append(f"id = :{param_name}")
            param_idx += 1

        elif isinstance(value, dict):
            # MongoDB comparison / logical operators
            for op, op_val in value.items():
                param_name = f"p{param_idx}"
                param_idx += 1

                if op == "$in":
                    if not op_val:
                        conditions.append("FALSE")
                    else:
                        placeholders = []
                        for v in op_val:
                            pn = f"p{param_idx}"
                            params[pn] = str(v)
                            placeholders.append(f":{pn}")
                            param_idx += 1
                        in_list = ", ".join(placeholders)
                        conditions.append(f"data->>{key!r} IN ({in_list})")

                elif op == "$ne":
                    params[param_name] = json.dumps(op_val)
                    conditions.append(f"data->>{key!r} != :{param_name}")

                elif op == "$lt":
                    if isinstance(op_val, datetime):
                        params[param_name] = str(op_val)
                        conditions.append(f"(data->>{key!r})::timestamptz < :{param_name}")
                    else:
                        params[param_name] = op_val
                        conditions.append(f"(data->>{key!r})::numeric < :{param_name}")

                elif op == "$gt":
                    if isinstance(op_val, datetime):
                        params[param_name] = str(op_val)
                        conditions.append(f"(data->>{key!r})::timestamptz > :{param_name}")
                    else:
                        params[param_name] = op_val
                        conditions.append(f"(data->>{key!r})::numeric > :{param_name}")

                elif op == "$lte":
                    if isinstance(op_val, datetime):
                        params[param_name] = str(op_val)
                        conditions.append(f"(data->>{key!r})::timestamptz <= :{param_name}")
                    else:
                        params[param_name] = op_val
                        conditions.append(f"(data->>{key!r})::numeric <= :{param_name}")

                elif op == "$gte":
                    if isinstance(op_val, datetime):
                        params[param_name] = str(op_val)
                        conditions.append(f"(data->>{key!r})::timestamptz >= :{param_name}")
                    else:
                        params[param_name] = op_val
                        conditions.append(f"(data->>{key!r})::numeric >= :{param_name}")

                elif op == "$exists":
                    if op_val:
                        conditions.append(f"data ? {key!r}")
                    else:
                        conditions.append(f"NOT (data ? {key!r})")

        elif value is None:
            conditions.append(f"(data->>{key!r}) IS NULL")

        else:
            param_name = f"p{param_idx}"
            # Coerce non-primitive types to string; pass primitives as-is for proper binding
            params[param_name] = (
                value if isinstance(value, (str, int, float, bool)) else str(value)
            )
            conditions.append(f"data->>{key!r} = :{param_name}")
            param_idx += 1

    return " AND ".join(conditions) if conditions else "TRUE"


# ---------------------------------------------------------------------------
# PgQuerySet — chainable query builder
# ---------------------------------------------------------------------------

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
        where = _translate_filters(self._filters, params)

        sql = f"SELECT id, data, created_at, updated_at FROM {table} WHERE {where}"

        if self._sort_fields:
            order_parts = []
            for f in self._sort_fields:
                if f.startswith(("-", "+")):
                    direction = "DESC" if f.startswith("-") else "ASC"
                    field = f[1:]
                else:
                    direction = "ASC"
                    field = f
                if field in ("created_at", "updated_at"):
                    order_parts.append(f"{field} {direction}")
                else:
                    order_parts.append(f"data->>{field!r} {direction}")
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
            rows = result.fetchall()
        return [self._model_cls._from_row(row) for row in rows]

    async def count(self) -> int:
        table = self._model_cls.get_collection_name()
        params: dict = {}
        where = _translate_filters(self._filters, params)
        sql = f"SELECT COUNT(*) FROM {table} WHERE {where}"
        factory = await get_session_factory()
        async with factory() as session:
            result = await session.execute(text(sql), params)
            return result.scalar() or 0

    def __await__(self):
        return self.to_list().__await__()


# ---------------------------------------------------------------------------
# PostgresDocument — drop-in Beanie Document replacement
# ---------------------------------------------------------------------------


class PostgresDocument:
    """Drop-in replacement for Beanie's Document using JSONB storage.

    Subclasses (which are also Pydantic models) define fields normally; the
    class stores them in the ``data`` JSONB column of the corresponding table.

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

    @classmethod
    def _from_row(cls, row: Any) -> PostgresDocument:
        """Reconstruct a model instance from a database row (id, data, ...)."""
        data: dict = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        data["id"] = row[0]
        if hasattr(cls, "model_validate"):
            return cls.model_validate(data)
        return cls(**data)

    def _to_data(self) -> dict:
        """Serialize this document to the JSONB *data* dict (excludes row columns)."""
        if hasattr(self, "model_dump"):
            return self.model_dump(mode="json", exclude={"id", "created_at", "updated_at"})
        import dataclasses  # noqa: PLC0415

        return dataclasses.asdict(self)  # type: ignore[arg-type]

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

    @classmethod
    async def insert(cls, document: PostgresDocument) -> PostgresDocument:
        await document.save()
        return document

    # ------------------------------------------------------------------
    # Instance-level persistence helpers
    # ------------------------------------------------------------------

    async def save(self) -> PostgresDocument:
        """Upsert this document into the database."""
        table = self.get_collection_name()
        now = datetime.now(UTC)

        # Resolve or generate the primary key
        doc_id = getattr(self, "id", None)
        if not doc_id:
            doc_id = str(uuid.uuid4())
            object.__setattr__(self, "id", doc_id)
        else:
            doc_id = str(doc_id)

        data = self._to_data()
        if "created_at" not in data:
            data["created_at"] = now.isoformat()
        data["updated_at"] = now.isoformat()

        sql = f"""
        INSERT INTO {table} (id, data, created_at, updated_at)
        VALUES (:id, :data::jsonb, :created_at, :updated_at)
        ON CONFLICT (id) DO UPDATE SET
            data = EXCLUDED.data,
            updated_at = EXCLUDED.updated_at
        """
        factory = await get_session_factory()
        async with factory() as session:
            await session.execute(
                text(sql),
                {
                    "id": doc_id,
                    "data": json.dumps(data, default=str),
                    "created_at": now,
                    "updated_at": now,
                },
            )
            await session.commit()
        return self

    async def delete(self) -> None:
        """Delete this document from the database."""
        table = self.get_collection_name()
        doc_id = str(getattr(self, "id", ""))
        if not doc_id:
            raise ValueError("Cannot delete a document without an id")
        factory = await get_session_factory()
        async with factory() as session:
            await session.execute(
                text(f"DELETE FROM {table} WHERE id = :id"),
                {"id": doc_id},
            )
            await session.commit()
