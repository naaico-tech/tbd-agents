"""Celery application instance.

Start a worker with:
    celery -A app.celery_app worker --loglevel=info --concurrency=4
"""

from celery import Celery

from app.config import settings

celery = Celery(
    "copilot_agent_hub",
    broker=settings.redis_url,
    backend=settings.redis_url,
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
