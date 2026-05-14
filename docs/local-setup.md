# Local Setup Notes

This page is retained for older links. The maintained setup guide is [Getting Started / Local Setup](getting-started/local-setup.md).

Current quick facts:

- Docker Compose is the recommended local path: `docker compose up --build`.
- The Flutter dashboard is served at `http://localhost:8000/dashboard`.
- The legacy dashboard is served at `http://localhost:8000/dashboard-legacy`.
- The SDK session timeout default is `SESSION_TIMEOUT=600`.
- `.env.example` starts Qdrant by default with `COMPOSE_PROFILES=qdrant`; remove or empty the variable if you want no vector-store container.
- For the all-PostgreSQL stack, set `COMPOSE_PROFILES=pgvector`, `DB_BACKEND=postgres`, `VECTOR_STORE_BACKEND=pgvector`, and `POSTGRES_URI=postgresql+asyncpg://postgres:postgres@pgvector:5432/tbd_agents`, then run `docker compose exec app alembic upgrade head` on first start.
