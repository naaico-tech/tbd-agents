"""Tests for the per-worker fastembed warm-up signal handler (PR3)."""

from __future__ import annotations

from unittest.mock import patch

from celery.signals import worker_process_init


def test_warm_embeddings_signal_invokes_ensure_loaded():
    """Firing ``worker_process_init`` must drive ``_ensure_loaded`` to completion."""
    # Importing the module wires up the signal handler.
    from app import celery_app  # noqa: F401  (side-effect import)
    from app.services import embeddings as embeddings_mod

    calls: list[bool] = []

    async def _fake_ensure_loaded(_self):
        calls.append(True)
        return True

    with patch.object(
        embeddings_mod.EmbeddingsService,
        "_ensure_loaded",
        _fake_ensure_loaded,
    ):
        worker_process_init.send(sender=None)

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
