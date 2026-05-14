#!/usr/bin/env python
"""Migrate data from MongoDB to PostgreSQL.

Usage:
    python scripts/migrate_mongo_to_postgres.py [--dry-run] [--collection NAME]
                                                 [--batch-size N] [--verbose]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import asyncpg
import motor.motor_asyncio
from bson import ObjectId

logger = logging.getLogger(__name__)

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB = "tbd_agents"
DEFAULT_POSTGRES_URI = "postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents"
DEFAULT_BATCH_SIZE = 500


# ---------------------------------------------------------------------------
# Column type specs — derived from _TABLE_DDL in app/db_postgres.py
# ---------------------------------------------------------------------------


@dataclass
class _ColSpec:
    """Typed column specification used to build INSERT statements."""

    name: str
    pg_type: str  # text | int | bool | float | timestamptz | jsonb | text_array | float_array


# Full per-collection column schemas (all non-id columns, in DDL order).
# Keep in sync with _TABLE_DDL in app/db_postgres.py.
COLLECTION_SCHEMAS: dict[str, list[_ColSpec]] = {
    "agents": [
        _ColSpec("name", "text"),
        _ColSpec("description", "text"),
        _ColSpec("system_prompt", "text"),
        _ColSpec("model", "text"),
        _ColSpec("mcp_server_ids", "text_array"),
        _ColSpec("mcp_server_tags", "text_array"),
        _ColSpec("tool_definitions", "jsonb"),
        _ColSpec("knowledge_source_ids", "text_array"),
        _ColSpec("knowledge_tags", "text_array"),
        _ColSpec("builtin_tools", "text_array"),
        _ColSpec("custom_tool_ids", "text_array"),
        _ColSpec("provider_id", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "chat_sessions": [
        _ColSpec("agent_id", "text"),
        _ColSpec("github_user", "text"),
        _ColSpec("title", "text"),
        _ColSpec("message_count", "int"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "chat_messages": [
        _ColSpec("session_id", "text"),
        _ColSpec("role", "text"),
        _ColSpec("content", "text"),
        _ColSpec("usage", "jsonb"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "memories": [
        _ColSpec("agent_id", "text"),
        _ColSpec("scope", "text"),
        _ColSpec("key", "text"),
        _ColSpec("value", "text"),
        _ColSpec("embedding", "float_array"),
        _ColSpec("metadata", "jsonb"),
        _ColSpec("ttl", "timestamptz"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "skills": [
        _ColSpec("name", "text"),
        _ColSpec("description", "text"),
        _ColSpec("instructions", "text"),
        _ColSpec("tags", "text_array"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "tokens": [
        _ColSpec("name", "text"),
        _ColSpec("encrypted_value", "text"),
        _ColSpec("description", "text"),
        _ColSpec("created_by", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "providers": [
        _ColSpec("name", "text"),
        _ColSpec("provider_type", "text"),
        _ColSpec("api_key_token_name", "text"),
        _ColSpec("base_url", "text"),
        _ColSpec("auth_type", "text"),
        _ColSpec("azure_api_version", "text"),
        _ColSpec("azure_deployment", "text"),
        _ColSpec("description", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "knowledge_items": [
        _ColSpec("source_id", "text"),
        _ColSpec("name", "text"),
        _ColSpec("content_type", "text"),
        _ColSpec("text_content", "text"),
        _ColSpec("file_id", "text"),
        _ColSpec("file_name", "text"),
        _ColSpec("file_size", "int"),
        _ColSpec("mime_type", "text"),
        _ColSpec("tags", "text_array"),
        _ColSpec("metadata", "jsonb"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "knowledge_sources": [
        _ColSpec("name", "text"),
        _ColSpec("description", "text"),
        _ColSpec("source_type", "text"),
        _ColSpec("connection_config", "jsonb"),
        _ColSpec("tags", "text_array"),
        _ColSpec("status", "text"),
        _ColSpec("last_error", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "custom_tools": [
        _ColSpec("name", "text"),
        _ColSpec("description", "text"),
        _ColSpec("source_code", "text"),
        _ColSpec("parameters_schema", "jsonb"),
        _ColSpec("env_config", "jsonb"),
        _ColSpec("tags", "text_array"),
        _ColSpec("is_enabled", "bool"),
        _ColSpec("is_plugin", "bool"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "guardrails": [
        _ColSpec("name", "text"),
        _ColSpec("description", "text"),
        _ColSpec("guardrail_type", "text"),
        _ColSpec("tags", "text_array"),
        _ColSpec("enabled", "bool"),
        _ColSpec("prompt_config", "jsonb"),
        _ColSpec("request_config", "jsonb"),
        _ColSpec("output_config", "jsonb"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "workflows": [
        _ColSpec("title", "text"),
        _ColSpec("agent_id", "text"),
        _ColSpec("github_user", "text"),
        _ColSpec("model", "text"),
        _ColSpec("max_turns", "int"),
        _ColSpec("current_turn", "int"),
        _ColSpec("session_id", "text"),
        _ColSpec("skill_ids", "text_array"),
        _ColSpec("skill_tags", "text_array"),
        _ColSpec("messages", "jsonb"),
        _ColSpec("logs", "jsonb"),
        _ColSpec("status", "text"),
        _ColSpec("output_format", "text"),
        _ColSpec("usage", "jsonb"),
        _ColSpec("infinite_session", "bool"),
        _ColSpec("caveman", "bool"),
        _ColSpec("bypass_memory", "bool"),
        _ColSpec("auto_memory", "bool"),
        _ColSpec("tsv_tool_results", "bool"),
        _ColSpec("reasoning_effort", "text"),
        _ColSpec("guardrail_ids", "text_array"),
        _ColSpec("guardrail_tags", "text_array"),
        _ColSpec("repo_url", "text"),
        _ColSpec("repo_branch", "text"),
        _ColSpec("repo_token_name", "text"),
        _ColSpec("credential_overrides", "jsonb"),
        _ColSpec("webhook_url", "text"),
        _ColSpec("error_webhook_url", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "task_executions": [
        _ColSpec("workflow_id", "text"),
        _ColSpec("prompt", "text"),
        _ColSpec("status", "text"),
        _ColSpec("celery_task_id", "text"),
        _ColSpec("worker", "text"),
        _ColSpec("model", "text"),
        _ColSpec("reasoning_effort", "text"),
        _ColSpec("tool_calls", "int"),
        _ColSpec("response", "text"),
        _ColSpec("progress", "jsonb"),
        _ColSpec("logs", "jsonb"),
        _ColSpec("messages", "jsonb"),
        _ColSpec("usage", "jsonb"),
        _ColSpec("started_at", "timestamptz"),
        _ColSpec("finished_at", "timestamptz"),
        _ColSpec("scheduled_agent_id", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "scheduled_agents": [
        _ColSpec("name", "text"),
        _ColSpec("workflow_id", "text"),
        _ColSpec("prompt", "text"),
        _ColSpec("interval_value", "int"),
        _ColSpec("interval_unit", "text"),
        _ColSpec("start_at", "timestamptz"),
        _ColSpec("end_at", "timestamptz"),
        _ColSpec("enabled", "bool"),
        _ColSpec("last_run_at", "timestamptz"),
        _ColSpec("next_run_at", "timestamptz"),
        _ColSpec("redbeat_key", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
    "mcp_servers": [
        _ColSpec("name", "text"),
        _ColSpec("transport_type", "text"),
        _ColSpec("connection_config", "jsonb"),
        _ColSpec("allowed_tools", "text_array"),
        _ColSpec("tags", "text_array"),
        _ColSpec("status", "text"),
        _ColSpec("last_error", "text"),
        _ColSpec("created_at", "timestamptz"),
        _ColSpec("updated_at", "timestamptz"),
    ],
}

# Ordered list preserved for display / iteration
COLLECTIONS: list[str] = list(COLLECTION_SCHEMAS.keys())

# Allowlist used to prevent SQL injection via collection_name
VALID_COLLECTIONS: frozenset[str] = frozenset(COLLECTION_SCHEMAS.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_postgres_uri(uri: str) -> str:
    """Strip +asyncpg scheme suffix so asyncpg can parse the DSN."""
    return uri.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )


def _serialize(obj: object) -> object:
    """Recursively convert BSON/datetime types to JSON-serializable forms."""
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


def _coerce(raw: Any, pg_type: str) -> Any:
    """Coerce a raw MongoDB value to the target PostgreSQL Python type."""
    if raw is None:
        return None
    if pg_type == "text":
        return str(raw)
    if pg_type == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    if pg_type == "float":
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None
    if pg_type == "bool":
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        return bool(raw)
    if pg_type == "timestamptz":
        if isinstance(raw, datetime):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                return None
        return None
    if pg_type == "jsonb":
        # Pass as JSON string; asyncpg accepts it with the ::jsonb cast in SQL
        return json.dumps(_serialize(raw))
    if pg_type == "text_array":
        if isinstance(raw, list):
            return [str(v) for v in raw]
        return []
    if pg_type == "float_array":
        if isinstance(raw, list):
            try:
                return [float(v) for v in raw]
            except (TypeError, ValueError):
                return []
        return []
    return raw


def _extract_row(doc: dict, col_specs: list[_ColSpec]) -> tuple[Any, ...]:
    """Return a parameter tuple for asyncpg from a MongoDB document.

    Tuple order: (id, <col_specs values in schema order>).
    """
    doc = dict(doc)
    doc_id = str(doc.get("_id", ""))
    values: list[Any] = [doc_id]
    for spec in col_specs:
        values.append(_coerce(doc.get(spec.name), spec.pg_type))
    return tuple(values)


def _build_insert(collection: str, col_specs: list[_ColSpec]) -> str:
    """Build the parameterised INSERT … ON CONFLICT … SQL for *collection*.

    Parameter ordering: $1 = id, $2 … $N = col_specs values.
    JSONB columns receive a ``::jsonb`` cast so asyncpg sends the raw JSON
    string and PostgreSQL performs the cast server-side.
    """
    all_cols = ["id"] + [s.name for s in col_specs]

    # Build positional placeholders ($1, $2::jsonb, …)
    placeholders: list[str] = ["$1"]  # id
    for i, spec in enumerate(col_specs, start=2):
        if spec.pg_type == "jsonb":
            placeholders.append(f"${i}::jsonb")
        else:
            placeholders.append(f"${i}")

    col_list = ", ".join(all_cols)
    val_list = ", ".join(placeholders)
    update_set = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in all_cols if c not in ("id", "created_at")
    )
    return (
        f"INSERT INTO {collection} ({col_list})\n"
        f"        VALUES ({val_list})\n"
        f"        ON CONFLICT (id) DO UPDATE SET {update_set}"
    )


async def migrate_collection(
    mongo_db: motor.motor_asyncio.AsyncIOMotorDatabase,
    pg_conn: asyncpg.Connection,
    collection_name: str,
    batch_size: int,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int, str]:
    """Migrate a single collection. Returns (mongo_count, migrated, status)."""
    # --- SQL injection guard: collection_name must be in the known allowlist ---
    if collection_name not in VALID_COLLECTIONS:
        raise ValueError(
            f"Unknown collection: {collection_name!r}. "
            f"Valid collections: {sorted(VALID_COLLECTIONS)}"
        )

    col_specs = COLLECTION_SCHEMAS[collection_name]
    insert_sql = _build_insert(collection_name, col_specs)

    collection = mongo_db[collection_name]
    mongo_count = await collection.count_documents({})

    print(f"[{collection_name}] Migrating {mongo_count} documents...")

    if mongo_count == 0:
        print(f"[{collection_name}] Nothing to migrate — skipping.")
        return mongo_count, 0, "SKIPPED"

    migrated = 0
    batch: list[tuple[Any, ...]] = []

    try:
        cursor = collection.find({})
        async for doc in cursor:
            try:
                row = _extract_row(doc, col_specs)
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to serialize doc %s: %s",
                    collection_name,
                    doc.get("_id"),
                    exc,
                )
                continue

            batch.append(row)

            if len(batch) >= batch_size:
                if not dry_run:
                    await pg_conn.executemany(insert_sql, batch)
                migrated += len(batch)
                if verbose:
                    print(
                        f"[{collection_name}]   Inserted batch — {migrated}/{mongo_count}"
                    )
                batch = []

        # Flush remaining rows
        if batch:
            if not dry_run:
                await pg_conn.executemany(insert_sql, batch)
            migrated += len(batch)
            if verbose:
                print(
                    f"[{collection_name}]   Inserted final batch — {migrated}/{mongo_count}"
                )

    except Exception as exc:
        logger.error("[%s] Migration failed: %s", collection_name, exc)
        return mongo_count, migrated, "ERROR"

    dry_label = " (dry-run)" if dry_run else ""
    print(f"[{collection_name}] Done — {migrated}/{mongo_count} documents{dry_label}.")
    return mongo_count, migrated, "OK"


def _print_summary(
    results: list[tuple[str, int, int, str]],
) -> None:
    """Print a formatted summary table."""
    col_w = max(len(r[0]) for r in results) + 2
    header = f"{'Collection':<{col_w}} {'Mongo':>10} {'Migrated':>10}  Status"
    print()
    print(header)
    print("-" * len(header))
    for collection_name, mongo_count, migrated, status in results:
        print(
            f"{collection_name:<{col_w}} {mongo_count:>10} {migrated:>10}  {status}"
        )
    print()


async def main(args: argparse.Namespace) -> int:
    mongo_uri = os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)
    mongo_db_name = os.environ.get("MONGO_DB_NAME", DEFAULT_MONGO_DB)
    postgres_uri = os.environ.get("POSTGRES_URI", DEFAULT_POSTGRES_URI)

    pg_dsn = _normalize_postgres_uri(postgres_uri)

    if args.collection:
        if args.collection not in VALID_COLLECTIONS:
            logger.error(
                "Unknown collection %r. Valid collections: %s",
                args.collection,
                sorted(VALID_COLLECTIONS),
            )
            return 1
        target_collections = [args.collection]
    else:
        target_collections = COLLECTIONS

    if args.dry_run:
        print("*** DRY RUN — no data will be written to PostgreSQL ***")
    print(f"Source : {mongo_uri} / {mongo_db_name}")
    print(f"Target : {pg_dsn}")
    print(f"Batch  : {args.batch_size}")
    print()

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    mongo_db = mongo_client[mongo_db_name]

    try:
        pg_conn = await asyncpg.connect(pg_dsn)
    except Exception as exc:
        logger.error("Cannot connect to PostgreSQL: %s", exc)
        mongo_client.close()
        return 1

    results: list[tuple[str, int, int, str]] = []

    try:
        for coll in target_collections:
            mongo_count, migrated, status = await migrate_collection(
                mongo_db=mongo_db,
                pg_conn=pg_conn,
                collection_name=coll,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                verbose=args.verbose,
            )
            results.append((coll, mongo_count, migrated, status))
    finally:
        await pg_conn.close()
        mongo_client.close()

    _print_summary(results)

    any_error = any(status == "ERROR" for _, _, _, status in results)
    return 1 if any_error else 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate MongoDB collections to PostgreSQL JSONB tables."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read from MongoDB but do not write to PostgreSQL.",
    )
    parser.add_argument(
        "--collection",
        metavar="NAME",
        help="Migrate only the named collection (default: all).",
    )
    parser.add_argument(
        "--batch-size",
        metavar="N",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Number of documents per INSERT batch (default: {DEFAULT_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-batch progress.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
    )
    sys.exit(asyncio.run(main(_parse_args())))
