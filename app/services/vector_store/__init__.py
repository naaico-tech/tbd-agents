"""Vector store abstraction layer for TBD Agents.

Provides a backend-agnostic interface (:class:`AbstractVectorStore`) with
concrete adapters for Qdrant and PostgreSQL + pgvector.  The active backend
is chosen at startup via :func:`get_vector_store` which reads application
settings and returns a singleton.

Quick start
-----------
.. code-block:: python

    from app.services.vector_store import get_vector_store, VectorPoint

    store = get_vector_store()          # None if backend not configured
    if store:
        await store.create_collection("my_col", vector_size=384)
        await store.upsert("my_col", [VectorPoint(id="doc-1", vector=[...])])
        hits = await store.search("my_col", query_vector=[...], limit=5)
        await store.close()

Exported symbols
----------------
``AbstractVectorStore``
    The abstract base class.  Use this for type annotations.
``VectorPoint``
    Dataclass representing a single storable vector with its ID and payload.
``SearchResult``
    Dataclass returned by :meth:`AbstractVectorStore.search` and
    :meth:`AbstractVectorStore.scroll`.
``VectorStoreBackend``
    :class:`~enum.StrEnum` of supported backend identifiers
    (``"qdrant"``, ``"pgvector"``).
``get_vector_store``
    Returns the application-wide singleton, or ``None`` if unconfigured.
``reset_vector_store``
    Resets the singleton (intended for test isolation).
"""

from app.services.vector_store.base import AbstractVectorStore, SearchResult, VectorPoint
from app.services.vector_store.factory import (
    VectorStoreBackend,
    get_vector_store,
    reset_vector_store,
)

__all__ = [
    "AbstractVectorStore",
    "VectorPoint",
    "SearchResult",
    "VectorStoreBackend",
    "get_vector_store",
    "reset_vector_store",
]
