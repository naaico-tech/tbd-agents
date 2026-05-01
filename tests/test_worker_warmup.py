"""Tests for the per-worker fastembed warm-up signal handler (PR3)."""

from __future__ import annotations

from unittest.mock import patch

from celery.signals import worker_process_init


def test_warm_embeddings_signal_invokes_ensure_loaded():
    """Firing ``worker_process_init`` must drive ``_ensure_loaded`` to completion."""
    import threading
    from unittest.mock import patch

    # Importing the module wires up the signal handler.
    from app import celery_app  # noqa: F401  (side-effect import)
    from app.services import embeddings as embeddings_mod

    calls: list[bool] = []
    spawned: list[threading.Thread] = []
    original_thread_start = threading.Thread.start

    async def _fake_ensure_loaded(_self):
        calls.append(True)
        return True

    def _capturing_start(self, *args, **kwargs):
        if getattr(self, "name", "") == "embeddings-warmup":
            spawned.append(self)
        return original_thread_start(self, *args, **kwargs)

    # Keep both patches active while the thread runs.
    with patch.object(
        embeddings_mod.EmbeddingsService, "_ensure_loaded", _fake_ensure_loaded
    ), patch.object(threading.Thread, "start", _capturing_start):
        worker_process_init.send(sender=None)
        # Join the warmup thread while still inside the patch context so the
        # mock is still in place when the async coroutine executes.
        for t in spawned:
            t.join(timeout=5)

    assert calls, "_ensure_loaded was not awaited by the signal handler"


def test_warm_embeddings_signal_swallows_failure():
    """A raising ``_ensure_loaded`` must not crash the worker boot."""
    from app import celery_app  # noqa: F401
    from app.services import embeddings as embeddings_mod

    async def _boom(_self):
        raise RuntimeError("model file missing")

    with patch.object(
        embeddings_mod.EmbeddingsService,
        "_ensure_loaded",
        _boom,
    ):
        # Must not raise.
        worker_process_init.send(sender=None)
