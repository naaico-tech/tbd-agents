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
from datetime import datetime

import asyncpg
import motor.motor_asyncio
from bson import ObjectId

logger = logging.getLogger(__name__)

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

DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_MONGO_DB = "tbd_agents"
DEFAULT_POSTGRES_URI = "postgresql+asyncpg://postgres:postgres@localhost:5432/tbd_agents"
DEFAULT_BATCH_SIZE = 500


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


def _extract_document(doc: dict) -> tuple[str, str, datetime | None, datetime | None]:
    """Return (id, data_json, created_at, updated_at) from a MongoDB document."""
    doc = dict(doc)
    raw_id = doc.pop("_id")
    doc_id = str(raw_id)

    created_at: datetime | None = doc.pop("created_at", None)
    updated_at: datetime | None = doc.pop("updated_at", None)

    # Ensure timestamps are proper datetime objects (they may already be)
    if isinstance(created_at, str):
        try:
            created_at = datetime.fromisoformat(created_at)
        except ValueError:
            created_at = None
    if isinstance(updated_at, str):
        try:
            updated_at = datetime.fromisoformat(updated_at)
        except ValueError:
            updated_at = None

    serialized = _serialize(doc)
    data_json = json.dumps(serialized)
    return doc_id, data_json, created_at, updated_at


async def migrate_collection(
    mongo_db: motor.motor_asyncio.AsyncIOMotorDatabase,
    pg_conn: asyncpg.Connection,
    collection_name: str,
    batch_size: int,
    dry_run: bool,
    verbose: bool,
) -> tuple[int, int, str]:
    """Migrate a single collection. Returns (mongo_count, migrated, status)."""
    collection = mongo_db[collection_name]
    mongo_count = await collection.count_documents({})

    print(f"[{collection_name}] Migrating {mongo_count} documents...")

    if mongo_count == 0:
        print(f"[{collection_name}] Nothing to migrate — skipping.")
        return mongo_count, 0, "SKIPPED"

    migrated = 0
    batch: list[tuple[str, str, datetime | None, datetime | None]] = []

    insert_sql = f"""
        INSERT INTO {collection_name} (id, data, created_at, updated_at)
        VALUES ($1, $2::jsonb, $3, $4)
        ON CONFLICT (id) DO UPDATE
            SET data = EXCLUDED.data,
                updated_at = now()
    """

    try:
        cursor = collection.find({})
        async for doc in cursor:
            try:
                row = _extract_document(doc)
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

    target_collections = (
        [args.collection] if args.collection else COLLECTIONS
    )

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
