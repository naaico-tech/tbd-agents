"""Factory and singleton accessor for the configured vector store backend.

Usage
-----
Anywhere in the application::

    from app.services.vector_store import get_vector_store

    store = get_vector_store()
    if store is not None:
        await store.upsert("agent_memories", points)

The backend is selected by ``settings.vector_store_backend``
(default: ``"qdrant"``).  The singleton is reset between tests via
:func:`reset_vector_store`.
"""

import logging
from enum import StrEnum

from app.config import settings
from app.services.vector_store.base import AbstractVectorStore

logger = logging.getLogger(__name__)

_instance: AbstractVectorStore | None = None


class VectorStoreBackend(StrEnum):
    """Supported vector store backend identifiers."""

    QDRANT = "qdrant"
    PGVECTOR = "pgvector"


def get_vector_store() -> AbstractVectorStore | None:
    """Return the configured vector store singleton.

    Returns ``None`` — rather than raising — when the required backend
    settings are absent (e.g. ``qdrant_url`` not set).  This allows semantic
    features to degrade gracefully without crashing the application.

    The instance is cached after the first successful call.  Call
    :func:`reset_vector_store` in tests to obtain a fresh instance.
    """
    global _instance
    if _instance is not None:
        return _instance

    backend = VectorStoreBackend(
        getattr(settings, "vector_store_backend", VectorStoreBackend.QDRANT)
    )

    if backend == VectorStoreBackend.PGVECTOR:
        dsn: str | None = getattr(settings, "pgvector_dsn", None)
        if not dsn:
            logger.debug(
                "get_vector_store: pgvector backend selected but 'pgvector_dsn' is not set"
            )
            return None
        from app.services.vector_store.pgvector_adapter import PgvectorAdapter

        prefix: str = getattr(settings, "pgvector_table_prefix", "vs")
        _instance = PgvectorAdapter(dsn=dsn, table_prefix=prefix)
        logger.info("VectorStore: using pgvector backend (dsn prefix=%s...)", dsn[:20])

    else:  # default: qdrant
        url: str | None = getattr(settings, "qdrant_url", None)
        if not url:
            logger.debug(
                "get_vector_store: qdrant backend selected but 'qdrant_url' is not set"
            )
            return None
        from app.services.vector_store.qdrant_adapter import QdrantAdapter

        api_key: str | None = getattr(settings, "qdrant_api_key", None)
        _instance = QdrantAdapter(url=url, api_key=api_key)
        logger.info("VectorStore: using qdrant backend (%s)", url)

    return _instance


def reset_vector_store() -> None:
    """Reset the singleton instance.

    Intended for use in tests to isolate each test from the shared singleton::

        from app.services.vector_store.factory import reset_vector_store

        def setup_function():
            reset_vector_store()
    """
    global _instance
    _instance = None
