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
    include=["app.tasks.agent_task"],
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
)

celery.autodiscover_tasks(["app.tasks"])


@worker_process_init.connect(weak=False)
def _init_worker_telemetry(**_kwargs):
    """Initialise OTEL tracing, Celery instrumentation, and Prometheus HTTP server."""
    from app.observability import init_telemetry

    init_telemetry()
    CeleryInstrumentor().instrument()

    # Expose Prometheus metrics on an HTTP port so they can be scraped.
    # Each worker process picks a port starting from WORKER_METRICS_PORT (default 9101).
    # With concurrency=4 each forked process gets the same call, but
    # start_http_server raises OSError if the port is taken, so we silently
    # skip subsequent forks.
    try:
        from prometheus_client import start_http_server

        port = int(os.environ.get("WORKER_METRICS_PORT", "9101"))
        start_http_server(port)
        logger.info("Worker Prometheus metrics server started on :%d", port)
    except OSError:
        # Port already bound by another worker process — expected with prefork.
        pass
