import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import (
    agents,
    chat,
    custom_tools,
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
from app.config import settings
from app.core import tools_loader
from app.db import init_db
from app.observability import celery_queue_length, init_telemetry
from app.services import memory_stm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

# Celery default queue name
_CELERY_QUEUE = "celery"


async def _poll_celery_queue(stop_event: asyncio.Event) -> None:
    """Periodically read the Celery queue length from Redis and update the gauge."""
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        while not stop_event.is_set():
            try:
                length = await r.llen(_CELERY_QUEUE)
                celery_queue_length.set(length)
            except Exception:
                logger.warning("Failed to read Celery queue length, resetting to 0", exc_info=True)
                celery_queue_length.set(0)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
    finally:
        await r.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Auto-load disk-based tools
    try:
        await tools_loader.load_tools_from_disk()
    except Exception as exc:
        logger.error("Failed to auto-load custom tools: %s", exc)

    # Warm up Short-Term Memory cache from MongoDB → Redis
    try:
        count = await memory_stm.warmup_all_agents()
        logger.info("STM warmup loaded %d agent(s) into Redis.", count)
    except Exception as exc:
        logger.warning("STM warmup failed (non-fatal): %s", exc)

    # Start background Celery queue-length poller
    stop_event = asyncio.Event()
    poller_task = asyncio.create_task(_poll_celery_queue(stop_event))

    yield

    # Graceful shutdown
    stop_event.set()
    try:
        await asyncio.wait_for(poller_task, timeout=15)
    except asyncio.TimeoutError:
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass
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
app.include_router(chat.router)
app.include_router(custom_tools.router)
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
