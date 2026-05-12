"""pgvector adapter for :class:`AbstractVectorStore`.

Uses ``asyncpg`` for async PostgreSQL connections and the ``pgvector`` Python
package to register the vector type codec.

``asyncpg`` and ``pgvector`` are included in the project dependencies and are
installed automatically with ``pip install -e .`` or ``uv sync``.

Table layout
------------
Each collection maps to a table named ``{table_prefix}_{sanitised_collection}``.
A metadata registry table ``{table_prefix}_collections`` tracks every
collection's ``vector_size`` and ``distance`` metric so that the correct
pgvector distance operator (``<=>``, ``<->``, ``<#>``) can be selected at
query time.

Distance operators
------------------
* ``cosine``  → ``<=>``   score = ``1 − (v <=> q)``
* ``euclid`` / ``l2``  → ``<->``   score = ``1 / (1 + (v <-> q))``
* ``dot`` / ``inner_product``  → ``<#>``   score = ``−(v <#> q)``
  (pgvector returns negative inner product, so we negate for a positive score)

Thread / concurrency safety
---------------------------
Pool creation is guarded by an ``asyncio.Lock`` to prevent duplicate
initialisation under concurrent coroutines.

.. note::
    ``numpy`` is required (it is a transitive dependency of ``fastembed``
    which is already in the project's required dependencies).  It is used to
    convert ``list[float]`` into the NumPy array that the ``pgvector`` asyncpg
    codec expects.
"""

import asyncio
import json
import logging
import re
from typing import Any

from app.services.vector_store.base import AbstractVectorStore, SearchResult, VectorPoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Distance-metric lookup table
# ---------------------------------------------------------------------------
# key → (ivfflat index ops class, SQL infix operator, score SQL expression)
# The score expression uses a ``{op}`` placeholder filled at runtime.
_DISTANCE_CONFIG: dict[str, tuple[str, str, str]] = {
    "cosine": (
        "vector_cosine_ops",
        "<=>",
        "1.0 - (vector {op} $1::vector)",
    ),
    "euclid": (
        "vector_l2_ops",
        "<->",
        "1.0 / (1.0 + (vector {op} $1::vector))",
    ),
    "l2": (
        "vector_l2_ops",
        "<->",
        "1.0 / (1.0 + (vector {op} $1::vector))",
    ),
    "dot": (
        "vector_ip_ops",
        "<#>",
        "-(vector {op} $1::vector)",  # <#> returns negative inner product
    ),
    "inner_product": (
        "vector_ip_ops",
        "<#>",
        "-(vector {op} $1::vector)",
    ),
}
_DEFAULT_DISTANCE = "cosine"


def _sanitize_name(name: str) -> str:
    """Convert *name* to a safe SQL identifier fragment (lowercase, ``[a-z0-9_]`` only)."""
    return re.sub(r"[^a-z0-9]", "_", name.lower())


def _build_filter_clauses(
    filters: dict[str, Any] | None,
    start_idx: int,
) -> tuple[list[str], list[Any]]:
    """Translate ``{"payload_key": value}`` into JSONB filter clauses.

    Returns
    -------
    clauses:
        List of SQL snippets like ``"payload->>'key' = $3"``.
    params:
        Corresponding positional parameter values (always coerced to ``str``
        because ``payload->>`` always returns text in PostgreSQL).

    .. note::
        Single quotes in key names are escaped (``''``) to prevent SQL
        injection.  Values are passed via positional parameters and are
        therefore fully safe.
    """
    if not filters:
        return [], []
    clauses: list[str] = []
    params: list[Any] = []
    for i, (key, value) in enumerate(filters.items(), start=start_idx):
        safe_key = key.replace("'", "''")  # escape single quotes in key literals
        clauses.append(f"payload->>'{safe_key}' = ${i}")
        params.append(str(value))
    return clauses, params


class PgvectorAdapter(AbstractVectorStore):
    """AbstractVectorStore backed by PostgreSQL + pgvector.

    Parameters
    ----------
    dsn:
        asyncpg-compatible DSN, e.g.
        ``"postgresql://user:pass@localhost:5432/mydb"``.
    table_prefix:
        Short prefix prepended to every collection table name (default
        ``"vs"``).  Keep it short to avoid hitting PostgreSQL's 63-byte
        identifier limit.
    pool_min:
        Minimum number of connections kept alive in the pool.
    pool_max:
        Maximum connections in the pool.
    """

    def __init__(
        self,
        dsn: str,
        table_prefix: str = "vs",
        pool_min: int = 2,
        pool_max: int = 10,
    ) -> None:
        self._dsn = dsn
        self._table_prefix = _sanitize_name(table_prefix)
        self._pool_min = pool_min
        self._pool_max = pool_max
        self._pool = None
        self._init_lock = asyncio.Lock()
        # Metadata registry table name derived from the table prefix
        self._meta_table = f"{self._table_prefix}_collections"
        # In-memory cache of { collection_name: {"vector_size": int, "distance": str} }
        self._meta_cache: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _table_name(self, collection: str) -> str:
        """Return the fully-qualified table name for *collection*."""
        return f"{self._table_prefix}_{_sanitize_name(collection)}"

    async def _ensure_pool(self):
        """Return the shared asyncpg pool, creating it on first call."""
        if self._pool is not None:
            return self._pool
        async with self._init_lock:
            if self._pool is not None:  # double-checked locking
                return self._pool

            import asyncpg
            from pgvector.asyncpg import register_vector

            self._pool = await asyncpg.create_pool(
                self._dsn,
                min_size=self._pool_min,
                max_size=self._pool_max,
                init=register_vector,  # registers the vector codec on each new connection
            )
            # Bootstrap the metadata registry table
            async with self._pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {self._meta_table} (
                        name        TEXT PRIMARY KEY,
                        vector_size INT  NOT NULL,
                        distance    TEXT NOT NULL,
                        created_at  TIMESTAMPTZ DEFAULT now()
                    )
                """)
            logger.debug(
                "PgvectorAdapter: pool created (min=%d, max=%d)", self._pool_min, self._pool_max
            )
        return self._pool

    async def _get_collection_meta(self, name: str) -> dict[str, Any] | None:
        """Return cached or freshly loaded metadata for *name*."""
        if name in self._meta_cache:
            return self._meta_cache[name]
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT vector_size, distance FROM {self._meta_table} WHERE name = $1", name
            )
        if row:
            meta = {"vector_size": row["vector_size"], "distance": row["distance"]}
            self._meta_cache[name] = meta
            return meta
        return None

    @staticmethod
    def _to_vector(v: list[float]):
        """Convert a ``list[float]`` to a NumPy array for the pgvector codec."""
        import numpy as np

        return np.array(v, dtype=np.float32)

    # ------------------------------------------------------------------
    # AbstractVectorStore implementation
    # ------------------------------------------------------------------

    async def create_collection(
        self, name: str, vector_size: int, distance: str = "cosine"
    ) -> None:
        """Create a table + ivfflat index for *name* if not already present."""
        pool = await self._ensure_pool()
        table = self._table_name(name)
        dist_key = distance.lower()
        ops_class, _, _ = _DISTANCE_CONFIG.get(dist_key, _DISTANCE_CONFIG[_DEFAULT_DISTANCE])

        async with pool.acquire() as conn:
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    id         TEXT        PRIMARY KEY,
                    vector     vector({vector_size}),
                    payload    JSONB       DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """)
            # ivfflat index — requires at least one row to be useful, but
            # CREATE INDEX IF NOT EXISTS is idempotent so safe to call early.
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS {table}_vector_idx
                    ON {table}
                    USING ivfflat (vector {ops_class})
                    WITH (lists = 100)
            """)
            await conn.execute(f"""
                INSERT INTO {self._meta_table} (name, vector_size, distance)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO UPDATE
                    SET vector_size = EXCLUDED.vector_size,
                        distance    = EXCLUDED.distance
            """, name, vector_size, distance)

        self._meta_cache[name] = {"vector_size": vector_size, "distance": distance}
        logger.info(
            "PgvectorAdapter: collection '%s' ready (table=%s, dim=%d, distance=%s)",
            name, table, vector_size, distance,
        )

    async def collection_exists(self, name: str) -> bool:
        """Return ``True`` if *name* is registered in the metadata table."""
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT 1 FROM {self._meta_table} WHERE name = $1", name
            )
        return row is not None

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Insert or overwrite *points* in *collection*."""
        pool = await self._ensure_pool()
        table = self._table_name(collection)
        async with pool.acquire() as conn:
            # Batch via executemany for efficiency
            await conn.executemany(
                f"""
                INSERT INTO {table} (id, vector, payload)
                VALUES ($1, $2, $3)
                ON CONFLICT (id) DO UPDATE
                    SET vector  = EXCLUDED.vector,
                        payload = EXCLUDED.payload
                """,
                [
                    (p.id, self._to_vector(p.vector), json.dumps(p.payload))
                    for p in points
                ],
            )

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Approximate nearest-neighbour search using the collection's distance metric."""
        import asyncpg

        pool = await self._ensure_pool()
        table = self._table_name(collection)

        meta = await self._get_collection_meta(collection)
        dist_key = (meta or {}).get("distance", _DEFAULT_DISTANCE).lower()
        _, op, score_tpl = _DISTANCE_CONFIG.get(dist_key, _DISTANCE_CONFIG[_DEFAULT_DISTANCE])
        score_expr = score_tpl.format(op=op)

        # $1 = query vector, $2 = limit; filter params start at $3
        where_clauses, filter_params = _build_filter_clauses(filters, start_idx=3)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT id, {score_expr} AS score, payload
            FROM   {table}
            {where_sql}
            ORDER  BY vector {op} $1::vector
            LIMIT  $2
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, self._to_vector(query_vector), limit, *filter_params)
        except asyncpg.UndefinedTableError:
            logger.warning("PgvectorAdapter: collection '%s' table not found during search", collection)  # noqa: E501
            return []

        return [
            SearchResult(
                id=row["id"],
                score=float(row["score"]),
                payload=dict(row["payload"]),
            )
            for row in rows
        ]

    async def scroll(
        self,
        collection: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Retrieve points ordered by insertion time (most-recent first).

        Supports both *limit* and integer *offset* for standard pagination.
        Filter params start at ``$3``; ``$1`` = limit, ``$2`` = offset.
        """
        import asyncpg

        pool = await self._ensure_pool()
        table = self._table_name(collection)

        # $1 = limit, $2 = offset; filter params start at $3
        where_clauses, filter_params = _build_filter_clauses(filters, start_idx=3)
        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        sql = f"""
            SELECT id, 0.0::float AS score, payload
            FROM   {table}
            {where_sql}
            ORDER  BY created_at DESC
            LIMIT  $1 OFFSET $2
        """
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(sql, limit, offset, *filter_params)
        except asyncpg.UndefinedTableError:
            logger.warning("PgvectorAdapter: collection '%s' table not found during scroll", collection)  # noqa: E501
            return []

        return [
            SearchResult(
                id=row["id"],
                score=0.0,
                payload=dict(row["payload"]),
            )
            for row in rows
        ]

    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete points by their string IDs."""
        pool = await self._ensure_pool()
        table = self._table_name(collection)
        async with pool.acquire() as conn:
            await conn.execute(f"DELETE FROM {table} WHERE id = ANY($1)", ids)

    async def delete_collection(self, collection: str) -> None:
        """Drop the collection table and remove its entry from the metadata table."""
        pool = await self._ensure_pool()
        table = self._table_name(collection)
        async with pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
            await conn.execute(f"DELETE FROM {self._meta_table} WHERE name = $1", collection)
        self._meta_cache.pop(collection, None)
        logger.info("PgvectorAdapter: deleted collection '%s' (table=%s)", collection, table)

    async def count(self, collection: str) -> int:
        """Return the number of rows in *collection*'s table."""
        pool = await self._ensure_pool()
        table = self._table_name(collection)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT COUNT(*) AS cnt FROM {table}")
        return int(row["cnt"])

    async def close(self) -> None:
        """Close all connections in the asyncpg pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            logger.debug("PgvectorAdapter: connection pool closed")
