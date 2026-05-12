"""Abstract base types and interface for vector store backends.

All concrete adapters (Qdrant, pgvector, …) must implement
:class:`AbstractVectorStore`.  Callers should program against this interface
exclusively so that the underlying storage engine can be swapped via
configuration without touching application logic.
"""

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class VectorPoint:
    """A single point to insert into or update within a vector collection.

    The *id* is always a plain string.  Each adapter converts it to whatever
    format the backend requires (e.g. a 64-bit integer for Qdrant) and stores
    the original string in the payload under ``_str_id`` so round-trips are
    lossless.
    """

    id: str
    vector: list[float]
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    """A single hit returned by :meth:`AbstractVectorStore.search` or
    :meth:`AbstractVectorStore.scroll`.

    *score* is a similarity value in the range ``[0, 1]`` where higher is more
    similar.  Scroll results always return ``score=0.0``.
    """

    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class AbstractVectorStore(abc.ABC):
    """Backend-agnostic vector store interface.

    All I/O methods are coroutines.  Implementations are responsible for
    connection management, type conversion, and any backend-specific quirks.
    The public API is intentionally minimal so that adapters stay easy to
    implement and test.

    Lifecycle
    ---------
    * Adapters use lazy initialisation — no network I/O occurs in
      ``__init__``.
    * Callers **must** call :meth:`close` when the store is no longer needed
      so that connections and thread pools are released cleanly.
    """

    @abc.abstractmethod
    async def create_collection(
        self, name: str, vector_size: int, distance: str = "cosine"
    ) -> None:
        """Create a collection / table if it does not already exist.

        Parameters
        ----------
        name:
            Logical collection name (e.g. ``"agent_memories"``).
        vector_size:
            Dimensionality of the stored vectors.
        distance:
            Similarity metric — one of ``"cosine"``, ``"euclid"`` / ``"l2"``,
            or ``"dot"`` / ``"inner_product"``.
        """

    @abc.abstractmethod
    async def collection_exists(self, name: str) -> bool:
        """Return ``True`` if *name* already exists in the backend."""

    @abc.abstractmethod
    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Insert or update *points* in *collection*.

        Existing points with the same ``id`` are overwritten in-place.
        """

    @abc.abstractmethod
    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Return the *limit* closest points to *query_vector*.

        Parameters
        ----------
        collection:
            Target collection name.
        query_vector:
            The embedding to search against.
        limit:
            Maximum number of results to return.
        filters:
            Optional ``{"payload_field": value}`` equality map.  Only points
            whose payload contains **all** the specified key/value pairs are
            considered.
        """

    @abc.abstractmethod
    async def scroll(
        self,
        collection: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Retrieve points ordered by recency/insertion order (no similarity).

        Useful for listing recent memories or browsing a collection without
        a query vector.  Returns results with ``score=0.0``.
        """

    @abc.abstractmethod
    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete points identified by their string *ids* from *collection*."""

    @abc.abstractmethod
    async def delete_collection(self, collection: str) -> None:
        """Drop *collection* and all of its data from the backend."""

    @abc.abstractmethod
    async def count(self, collection: str) -> int:
        """Return the total number of points stored in *collection*."""

    @abc.abstractmethod
    async def close(self) -> None:
        """Release open connections / thread pools / file handles."""
