"""Celery application instance.

Start a worker with:
    celery -A app.celery_app worker --loglevel=info --concurrency=4
"""

import logging
import os

from celery import Celery
from celery.signals import worker_process_init
from kombu import Queue
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from app.config import settings

logger = logging.getLogger(__name__)

# ── Queue-routing constants (used by index pipeline and tests) ───────────────

INDEX_ORCHESTRATOR_TASK_NAME = "run_index_repository_job"
INDEX_SHARD_TASK_NAME = "app.tasks.index_repository_task.index_shard"

celery = Celery(
    "copilot_agent_hub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.agent_task",
        "app.tasks.scheduled_trigger",
        "app.tasks.index_repository_task",
        "app.tasks.sync_repository_task",
    ],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # One task at a time per worker — agent tasks are long-running
    worker_prefetch_multiplier=1,
    # Re-queue tasks if worker is killed mid-execution
    task_acks_late=True,
    # Reject tasks on worker shutdown so they're re-queued
    task_reject_on_worker_lost=True,
    # RedBeat: store Celery Beat schedules in Redis so they are dynamic
    # and persistent across container restarts.
    redbeat_redis_url=settings.redis_url,
    beat_scheduler="redbeat.RedBeatScheduler",
    beat_max_loop_interval=5,  # seconds between Beat scheduler iterations
    # ── Queue topology ──────────────────────────────────────────────────────
    task_default_queue="default",
    task_queues=[
        Queue("default"),
        Queue("indexing"),
        Queue("embeddings"),
    ],
    task_routes={
        INDEX_ORCHESTRATOR_TASK_NAME: {"queue": "indexing"},
        INDEX_SHARD_TASK_NAME: {"queue": "embeddings"},
    },
)

celery.autodiscover_tasks(["app.tasks"])


@worker_process_init.connect(weak=False)
def _init_worker_telemetry(**_kwargs):
    """Initialise OTEL tracing, Celery instrumentation, and Prometheus HTTP server."""
    from app.observability import init_telemetry

    init_telemetry()
    CeleryInstrumentor().instrument()

    # Expose Prometheus metrics on an HTTP port so they can be scraped.
    # PROMETHEUS_MULTIPROC_DIR must be set (see docker-compose.yml) so that
    # metrics recorded in every forked worker process are aggregated by a
    # single MultiProcessCollector.  Only the first process can bind the
    # port; subsequent forks skip via the OSError handler.
    try:
        from prometheus_client import CollectorRegistry, start_http_server
        from prometheus_client.multiprocess import MultiProcessCollector

        port = int(os.environ.get("WORKER_METRICS_PORT", "9101"))
        registry = CollectorRegistry()
        MultiProcessCollector(registry)
        start_http_server(port, registry=registry)
        logger.info("Worker Prometheus metrics server started on :%d", port)
    except (OSError, ValueError):
        # OSError: port already bound by another worker process — expected with prefork.
        # ValueError: PROMETHEUS_MULTIPROC_DIR not set — metrics disabled in this env.
        pass


@worker_process_init.connect(weak=False)
def _warm_embeddings(**_kwargs):
    """Pre-load fastembed model weights before the first task runs."""
    import asyncio

    from app.services.embeddings import EmbeddingsService

    async def _run():
        try:
            await EmbeddingsService()._ensure_loaded()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Embeddings warmup failed (non-fatal): %s", exc)

    asyncio.run(_run())
