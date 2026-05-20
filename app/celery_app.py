"""Celery application instance.

Start a worker with:
    celery -A app.celery_app worker --loglevel=info --concurrency=4
"""

import logging
import os

from celery import Celery
from celery.signals import worker_process_init
from opentelemetry.instrumentation.celery import CeleryInstrumentor

from app.config import settings

logger = logging.getLogger(__name__)

celery = Celery(
    "copilot_agent_hub",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks.agent_task", "app.tasks.scheduled_trigger", "app.tasks.codegraph_tasks"],
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
)

celery.autodiscover_tasks(["app.tasks"])


@worker_process_init.connect(weak=False)
def _prewarm_embeddings(**_kwargs):
    """Pre-load the fastembed model in each worker process immediately after forking.

    Without this the model loads lazily on the first task that needs semantic
    memory retrieval, causing per-task HuggingFace cache-validation HTTP
    requests and a blocking model-load delay.  Loading here means all of that
    happens once at worker startup instead.
    """
    if not settings.embeddings_enabled:
        return
    try:
        from app.services.embeddings import embeddings_service

        model = embeddings_service._load_model(settings.embeddings_model)
        embeddings_service._model = model
        logger.info(
            "Embeddings model '%s' pre-warmed in worker process", settings.embeddings_model
        )
    except Exception as exc:
        logger.warning("Embeddings model pre-warm failed (will load lazily): %s", exc)


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
    except OSError:
        # Port already bound by another worker process — expected with prefork.
        pass
