"""Pure-config test for the Celery queue topology.

Locks down the routing introduced by ``embeddings-queue-split``: the
indexing orchestrator must land on the ``indexing`` queue and the
default queue stays ``default`` for backward compatibility with
existing (agent / scheduled / sync) tasks.
"""

from __future__ import annotations

from app.celery_app import (
    INDEX_ORCHESTRATOR_TASK_NAME,
    INDEX_SHARD_TASK_NAME,
    celery,
)


def test_task_default_queue_is_default():
    assert celery.conf.task_default_queue == "default"


def test_named_queues_are_declared():
    queue_names = {q.name for q in celery.conf.task_queues}
    assert {"default", "indexing", "embeddings"}.issubset(queue_names)


def test_orchestrator_routed_to_indexing_queue():
    routes = celery.conf.task_routes
    assert routes is not None
    entry = routes[INDEX_ORCHESTRATOR_TASK_NAME]
    assert entry["queue"] == "indexing"


def test_orchestrator_legacy_short_name_also_routed():
    """The orchestrator task is currently registered as
    ``run_index_repository_job`` (no module prefix); both names must
    route to ``indexing`` so the route still matches today.
    """
    routes = celery.conf.task_routes
    assert routes["run_index_repository_job"]["queue"] == "indexing"


def test_shard_task_routed_to_embeddings_queue():
    """Placeholder route for PR3's ``chord-shard-fanout``. The task
    itself isn't registered yet — Celery is fine with that."""
    routes = celery.conf.task_routes
    entry = routes[INDEX_SHARD_TASK_NAME]
    assert entry["queue"] == "embeddings"
