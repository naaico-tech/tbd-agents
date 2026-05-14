# Migration & Upgrade Guide

This guide covers how to upgrade TBD Agents between versions, handle database migrations, and avoid common pitfalls.

---

## General Upgrade Steps

1. **Read the changelog** — check the [GitHub releases](https://github.com/naaico-tech/tbd-agents/releases) for breaking changes.
2. **Back up your database** — snapshot MongoDB or PostgreSQL, depending on `DB_BACKEND`.
3. **Pull the new image or code** — update your Docker image or `git pull` the latest tag.
4. **Run database migrations** — apply any schema changes (see below).
5. **Restart services** — restart the API server and Celery workers.

### Docker Compose upgrade

```bash
# Pull latest images
docker compose pull

# Restart with the new version
docker compose down
docker compose up -d
```

### Local development upgrade

```bash
git pull origin master
uv sync          # or: pip install -e ".[dev]"
```

---

## Database Migrations

TBD Agents supports two document-store backends:

- **MongoDB** with Beanie ODM (`DB_BACKEND=mongo`, the default)
- **PostgreSQL** with Alembic-managed schema (`DB_BACKEND=postgres`)

MongoDB documents are schema-flexible — new fields with defaults are added automatically when existing documents are read. PostgreSQL deployments must run Alembic migrations after upgrades that include schema changes.

### When migration is NOT needed

- Adding a new field with a default value (Beanie populates it on read)
- Adding a new collection (Beanie creates it on first write)
- Adding new enum values to an existing enum field

### When migration IS needed

- Renaming a field
- Changing a field's type
- Removing a field that is indexed
- Restructuring nested documents

### Running a manual migration

For one-off migrations, use a Python script against the database:

```python
"""Example: rename a field across all documents."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def migrate():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client["tbd_agents"]

    # Rename 'old_field' to 'new_field' in the agents collection
    result = await db.agents.update_many(
        {"old_field": {"$exists": True}},
        {"$rename": {"old_field": "new_field"}},
    )
    print(f"Modified {result.modified_count} documents")
    client.close()

asyncio.run(migrate())
```

### PostgreSQL / Alembic migrations

For PostgreSQL deployments, run:

```bash
docker compose exec app alembic upgrade head
docker compose exec app alembic current
```

See the [PostgreSQL Backend guide](../guide/postgres-backend.md) for first-run setup, migration from MongoDB, and verification scripts.

!!! warning "MongoDB database name during backend migration"
    The app default MongoDB database is `copilot_agent_hub`. Some migration script
    examples historically used `tbd_agents`; set `MONGO_DB_NAME=copilot_agent_hub`
    explicitly when migrating from the default app deployment.

### MongoDB backup / restore

```bash
# Backup
docker compose exec mongo mongodump --db tbd_agents --out /dump

# Restore
docker compose exec mongo mongorestore --db tbd_agents /dump/tbd_agents
```

---

## Version-Specific Notes

### v0.1.0

This is the first public release of TBD Agents. No migration is needed — start fresh.

See the [CHANGELOG](https://github.com/naaico-tech/tbd-agents/blob/master/CHANGELOG.md) for a full list of features included in this release.

---

## Helm / Kubernetes Upgrades

If deploying via the Helm chart:

```bash
# Update chart values
helm upgrade tbd-agents ./helm/tbd-agents \
  --set image.tag=0.1.0 \
  --reuse-values

# Verify rollout
kubectl rollout status deployment/tbd-agents
```

!!! warning "StatefulSet changes"
    If the chart changes volume claims or StatefulSet specs, you may need to delete and recreate the StatefulSet. Check the chart changelog before upgrading.

---

## Rollback

If an upgrade fails:

```bash
# Docker Compose — restore from backup
docker compose down
# Restore MongoDB from dump (see above)
docker compose up -d

# Helm — revert to previous release
helm rollback tbd-agents
```

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ValidationError` on startup | New required field without default | Run a migration script to backfill the field |
| SSE stream not connecting | Redis not running or URL misconfigured | Check `REDIS_URL` and verify Redis is reachable |
| Knowledge retrieval empty | Qdrant connection in `error` status | Call `/api/knowledge-sources/<ID>/test` and check `last_error` |
| Celery workers not starting | Mismatched package versions | Ensure API and workers run the same code version |
