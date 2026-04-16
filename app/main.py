import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import (
    agents,
    guardrails,
    health,
    knowledge_items,
    knowledge_sources,
    mcps,
    memories,
    models,
    providers,
    skills,
    tasks,
    tokens,
    workflows,
)
from app.db import init_db
from app.observability import init_telemetry
from app.services import memory_stm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Warm up Short-Term Memory cache from MongoDB → Redis
    try:
        count = await memory_stm.warmup_all_agents()
        logger.info("STM warmup loaded %d agent(s) into Redis.", count)
    except Exception as exc:
        logger.warning("STM warmup failed (non-fatal): %s", exc)

    yield

    # Graceful shutdown: close STM Redis connection
    await memory_stm.close()


app = FastAPI(
    title="TBD Agent",
    description="Multi-agent API hub powered by GitHub Copilot Models API with MCP support",
    version="0.1.0",
    lifespan=lifespan,
)

# ── Observability ────────────────────────────────────────────────────────────
init_telemetry(app)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

app.include_router(health.router)
app.include_router(agents.router)
app.include_router(guardrails.router)
app.include_router(providers.router)
app.include_router(skills.router)
app.include_router(knowledge_sources.router)
app.include_router(knowledge_items.router)
app.include_router(memories.router)
app.include_router(mcps.router)
app.include_router(models.router)
app.include_router(tokens.router)
app.include_router(tasks.router)
app.include_router(workflows.router)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/dashboard")
async def dashboard():
    return FileResponse(STATIC_DIR / "index.html")
