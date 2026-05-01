import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import (
    agents,
    chat,
    custom_tools,
    export_import,
    guardrails,
    health,
    knowledge_items,
    knowledge_sources,
    mcps,
    memories,
    models,
    providers,
    scheduled_agents,
    skills,
    tasks,
    tokens,
    workflows,
)
from app.config import settings
from app.core import plugin_loader
from app.db import init_db
from app.observability import celery_queue_length, init_telemetry
from app.services import memory_stm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
LEGACY_STATIC_DIR = APP_DIR / "static"
FLUTTER_STATIC_CANDIDATES = (
    APP_DIR / "dashboard",
    APP_DIR.parent / "frontend" / "build" / "web",
)

# Celery default queue name
_CELERY_QUEUE = "celery"


def _resolve_flutter_static_dir() -> Path | None:
    """Return the first available Flutter web build directory."""
    for candidate in FLUTTER_STATIC_CANDIDATES:
        if (candidate / "index.html").is_file():
            return candidate
    return None


FLUTTER_STATIC_DIR = _resolve_flutter_static_dir()


def _resolve_dashboard_path(request_path: str) -> Path | None:
    """Resolve a dashboard asset path with SPA fallback for nested routes."""
    if FLUTTER_STATIC_DIR is None:
        return None

    index_path = FLUTTER_STATIC_DIR / "index.html"
    flutter_root = FLUTTER_STATIC_DIR.resolve()
    normalized_path = request_path.lstrip("/")
    if not normalized_path:
        return index_path

    requested_path = (FLUTTER_STATIC_DIR / normalized_path).resolve()
    try:
        relative_path = requested_path.relative_to(flutter_root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Dashboard asset not found") from exc

    if any(part.startswith(".") for part in relative_path.parts):
        raise HTTPException(status_code=404, detail="Dashboard asset not found")

    if requested_path.is_file():
        return requested_path

    if Path(normalized_path).suffix:
        raise HTTPException(status_code=404, detail="Dashboard asset not found")

    return index_path


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
            except TimeoutError:
                pass
    finally:
        await r.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized.")

    # Auto-register GitNexus MCP server if GITNEXUS_URL is configured
    try:
        from app.services.gitnexus_seeder import seed_gitnexus_mcp
        await seed_gitnexus_mcp()
    except Exception as exc:
        logger.warning("GitNexus MCP seeding failed (non-fatal): %s", exc)

    # Load plugins from app/plugins.yaml registry
    try:
        await plugin_loader.load_plugins_from_config()
    except Exception as exc:
        logger.error("Failed to load plugins: %s", exc)

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
    except TimeoutError:
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
app.include_router(export_import.router)
app.include_router(guardrails.router)
app.include_router(providers.router)
app.include_router(scheduled_agents.router)
app.include_router(skills.router)
app.include_router(knowledge_sources.router)
app.include_router(knowledge_items.router)
app.include_router(memories.router)
app.include_router(mcps.router)
app.include_router(models.router)
app.include_router(tokens.router)
app.include_router(tasks.router)
app.include_router(workflows.router)

app.mount("/static", StaticFiles(directory=str(LEGACY_STATIC_DIR)), name="static")


@app.get("/dashboard-new-ui", include_in_schema=False)
@app.get("/dashboard-new-ui/{asset_path:path}", include_in_schema=False)
async def dashboard_new_ui(asset_path: str = ""):
    resolved_path = _resolve_dashboard_path(asset_path)
    if resolved_path is not None:
        return FileResponse(resolved_path)
    return FileResponse(LEGACY_STATIC_DIR / "index.html")


@app.get("/dashboard", include_in_schema=False)
@app.get("/dashboard-legacy", include_in_schema=False)
async def dashboard_legacy():
    return FileResponse(LEGACY_STATIC_DIR / "index.html")
