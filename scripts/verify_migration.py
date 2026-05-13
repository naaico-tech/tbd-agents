#!/usr/bin/env python
"""Verify that MongoDB data has been correctly migrated to PostgreSQL.

Usage:
    python scripts/verify_migration.py [--collection NAME]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import sys

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
SPOT_CHECK_SAMPLE = 3


def _normalize_postgres_uri(uri: str) -> str:
    """Strip +asyncpg scheme suffix so asyncpg can parse the DSN."""
    return uri.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgres+asyncpg://", "postgres://"
    )


def _serialize(obj: object) -> object:
    """Recursively convert BSON/datetime types to JSON-serializable forms."""
    from datetime import datetime

    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    return obj


async def _get_random_mongo_ids(
    collection: motor.motor_asyncio.AsyncIOMotorCollection,
    n: int,
) -> list[str]:
    """Return up to *n* random document IDs from the collection."""
    total = await collection.count_documents({})
    if total == 0:
        return []
    sample_size = min(n, total)
    # Use $sample aggregation for a random subset
    pipeline = [{"$sample": {"size": sample_size}}, {"$project": {"_id": 1}}]
    cursor = collection.aggregate(pipeline)
    ids = [str(doc["_id"]) async for doc in cursor]
    return ids


async def verify_collection(
    mongo_db: motor.motor_asyncio.AsyncIOMotorDatabase,
    pg_conn: asyncpg.Connection,
    collection_name: str,
) -> tuple[bool, list[str]]:
    """
    Verify one collection.

    Returns (all_ok, list_of_failure_messages).
    """
    failures: list[str] = []
    mongo_coll = mongo_db[collection_name]

    # --- Count comparison ---
    mongo_count = await mongo_coll.count_documents({})
    pg_row = await pg_conn.fetchrow(
        f"SELECT COUNT(*) AS n FROM {collection_name}"  # noqa: S608
    )
    pg_count = pg_row["n"] if pg_row else 0

    match_symbol = "✓ MATCH" if mongo_count == pg_count else "✗ MISMATCH"
    print(
        f"[{collection_name}] MongoDB: {mongo_count:>8}  PostgreSQL: {pg_count:>8}  {match_symbol}"
    )

    if mongo_count != pg_count:
        failures.append(
            f"{collection_name}: count mismatch — Mongo {mongo_count} vs PG {pg_count}"
        )

    # --- Spot-check ---
    sample_ids = await _get_random_mongo_ids(mongo_coll, SPOT_CHECK_SAMPLE)

    for doc_id in sample_ids:
        # Fetch from Mongo (try both ObjectId and plain string)
        try:
            mongo_doc = await mongo_coll.find_one({"_id": ObjectId(doc_id)})
        except Exception:
            mongo_doc = await mongo_coll.find_one({"_id": doc_id})

        if mongo_doc is None:
            failures.append(f"{collection_name}/{doc_id}: not found in MongoDB during spot-check")
            continue

        # Check existence in Postgres
        pg_row = await pg_conn.fetchrow(
            f"SELECT id, data FROM {collection_name} WHERE id = $1",  # noqa: S608
            doc_id,
        )
        if pg_row is None:
            failures.append(f"{collection_name}/{doc_id}: missing in PostgreSQL")
            print(f"  ✗ spot-check {doc_id} — missing in PostgreSQL")
            continue

        # Verify data payload (strip Mongo _id and known timestamp fields before comparing)
        mongo_data = dict(mongo_doc)
        mongo_data.pop("_id", None)
        mongo_data.pop("created_at", None)
        mongo_data.pop("updated_at", None)
        mongo_serialized = _serialize(mongo_data)

        raw = pg_row["data"]
        pg_data = json.loads(raw) if isinstance(raw, str) else dict(raw)

        if mongo_serialized != pg_data:
            failures.append(
                f"{collection_name}/{doc_id}: data mismatch between MongoDB and PostgreSQL"
            )
            print(f"  ✗ spot-check {doc_id} — data mismatch")
        else:
            print(f"  ✓ spot-check {doc_id} — OK")

    return len(failures) == 0, failures


async def main(args: argparse.Namespace) -> int:
    mongo_uri = os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)
    mongo_db_name = os.environ.get("MONGO_DB_NAME", DEFAULT_MONGO_DB)
    postgres_uri = os.environ.get("POSTGRES_URI", DEFAULT_POSTGRES_URI)

    pg_dsn = _normalize_postgres_uri(postgres_uri)

    target_collections = [args.collection] if args.collection else COLLECTIONS

    print(f"Source : {mongo_uri} / {mongo_db_name}")
    print(f"Target : {pg_dsn}")
    print()

    mongo_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    mongo_db = mongo_client[mongo_db_name]

    try:
        pg_conn = await asyncpg.connect(pg_dsn)
    except Exception as exc:
        logger.error("Cannot connect to PostgreSQL: %s", exc)
        mongo_client.close()
        return 1

    all_failures: list[str] = []

    try:
        for coll in target_collections:
            try:
                ok, failures = await verify_collection(
                    mongo_db=mongo_db,
                    pg_conn=pg_conn,
                    collection_name=coll,
                )
                all_failures.extend(failures)
            except Exception as exc:
                msg = f"{coll}: verification error — {exc}"
                logger.error(msg)
                all_failures.append(msg)
    finally:
        await pg_conn.close()
        mongo_client.close()

    # --- Final summary ---
    print()
    print("=" * 60)
    if all_failures:
        print(f"RESULT: FAIL — {len(all_failures)} issue(s) found")
        for failure in all_failures:
            print(f"  • {failure}")
        return 1
    else:
        print("RESULT: PASS — all collections verified successfully ✓")
        return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify MongoDB → PostgreSQL migration correctness."
    )
    parser.add_argument(
        "--collection",
        metavar="NAME",
        help="Verify only the named collection (default: all).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s  %(message)s",
    )
    # Seed random for reproducibility within a run (optional)
    random.seed()
    sys.exit(asyncio.run(main(_parse_args())))
