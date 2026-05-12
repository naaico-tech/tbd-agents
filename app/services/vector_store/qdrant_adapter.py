"""Qdrant adapter for :class:`AbstractVectorStore`.

Wraps ``qdrant-client`` (already a project dependency) and translates the
backend-agnostic API into Qdrant-specific calls.

Key implementation notes
------------------------
* String IDs are converted to deterministic 64-bit integers via a SHA-256
  hash truncated to int64.  The original string is stored in the point
  payload under ``_str_id`` so that round-trips through search/scroll are
  lossless.
* The client is created lazily on the first operation.
* A ``threading.Lock``-free double-checked pattern using ``asyncio.Lock``
  prevents duplicate client initialisation under concurrent async calls.
"""

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, Any

from app.services.vector_store.base import AbstractVectorStore, SearchResult, VectorPoint

if TYPE_CHECKING:  # pragma: no cover
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Filter

logger = logging.getLogger(__name__)

# Maps the distance string used in our public API to the Qdrant Distance enum
# member name (accessed via ``getattr(Distance, ...)``).
_DISTANCE_ENUM: dict[str, str] = {
    "cosine": "COSINE",
    "euclid": "EUCLID",
    "l2": "EUCLID",
    "dot": "DOT",
    "inner_product": "DOT",
}

# Payload key used to preserve the original string ID across storage round-trips
_STR_ID_KEY = "_str_id"


class QdrantAdapter(AbstractVectorStore):
    """AbstractVectorStore backed by an async Qdrant client.

    Parameters
    ----------
    url:
        Qdrant service URL (e.g. ``"http://localhost:6333"``).
    api_key:
        Optional Qdrant API key for authenticated deployments.
    """

    def __init__(self, url: str, api_key: str | None = None) -> None:
        self._url = url
        self._api_key = api_key
        self._client: AsyncQdrantClient | None = None
        self._init_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> "AsyncQdrantClient":
        """Return the shared Qdrant client, creating it if necessary."""
        if self._client is not None:
            return self._client
        async with self._init_lock:
            if self._client is not None:  # double-checked locking
                return self._client
            from qdrant_client import AsyncQdrantClient

            self._client = AsyncQdrantClient(url=self._url, api_key=self._api_key)
            logger.debug("QdrantAdapter: connected to %s", self._url)
        return self._client

    @staticmethod
    def _str_to_point_id(str_id: str) -> int:
        """Convert a string ID to a deterministic Qdrant-compatible integer.

        Uses SHA-256 (truncated to 64 bits) so the result is stable across
        process restarts regardless of ``PYTHONHASHSEED``.
        """
        return int(hashlib.sha256(str_id.encode()).hexdigest()[:16], 16) % (2**63)

    def _build_qdrant_filter(self, filters: dict[str, Any]) -> "Filter":
        """Translate a ``{"field": value}`` dict to a Qdrant :class:`Filter`."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filters.items()
            ]
        )

    @staticmethod
    def _record_to_result(point: Any) -> SearchResult:
        """Convert a Qdrant ``ScoredPoint`` or ``Record`` to a :class:`SearchResult`."""
        payload: dict[str, Any] = dict(point.payload or {})
        str_id = payload.pop(_STR_ID_KEY, str(point.id))
        score: float = getattr(point, "score", 0.0) or 0.0
        return SearchResult(id=str(str_id), score=score, payload=payload)

    # ------------------------------------------------------------------
    # AbstractVectorStore implementation
    # ------------------------------------------------------------------

    async def create_collection(
        self, name: str, vector_size: int, distance: str = "cosine"
    ) -> None:
        """Create a Qdrant collection if it does not already exist."""
        from qdrant_client.models import Distance, VectorParams

        enum_name = _DISTANCE_ENUM.get(distance.lower(), "COSINE")
        qdrant_distance = getattr(Distance, enum_name)

        client = await self._ensure_client()
        if not await self.collection_exists(name):
            await client.create_collection(
                name,
                vectors_config=VectorParams(size=vector_size, distance=qdrant_distance),
            )
            logger.info(
                "QdrantAdapter: created collection '%s' (dim=%d, distance=%s)",
                name,
                vector_size,
                distance,
            )

    async def collection_exists(self, name: str) -> bool:
        """Return ``True`` if the named Qdrant collection exists."""
        client = await self._ensure_client()
        response = await client.get_collections()
        return any(c.name == name for c in response.collections)

    async def upsert(self, collection: str, points: list[VectorPoint]) -> None:
        """Upsert *points* into *collection*.

        The original string ID is stored in the payload under ``_str_id`` for
        lossless retrieval.
        """
        from qdrant_client.models import PointStruct

        client = await self._ensure_client()
        qdrant_points = [
            PointStruct(
                id=self._str_to_point_id(p.id),
                vector=p.vector,
                payload={**p.payload, _STR_ID_KEY: p.id},
            )
            for p in points
        ]
        await client.upsert(collection_name=collection, points=qdrant_points)

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        limit: int = 10,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Semantic similarity search via ``query_points``."""
        client = await self._ensure_client()
        query_filter = self._build_qdrant_filter(filters) if filters else None
        response = await client.query_points(
            collection_name=collection,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [self._record_to_result(pt) for pt in response.points]

    async def scroll(
        self,
        collection: str,
        limit: int = 10,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Retrieve points in insertion order without similarity scoring.

        .. note::
            Qdrant uses cursor-based scroll pagination internally.  Integer
            *offset* is emulated by fetching ``offset + limit`` points and
            slicing the tail.  This is efficient for small offsets (< ~1 000)
            which cover all practical use-cases in this project.
        """
        client = await self._ensure_client()
        query_filter = self._build_qdrant_filter(filters) if filters else None
        fetch_limit = offset + limit if offset > 0 else limit
        records, _ = await client.scroll(
            collection_name=collection,
            scroll_filter=query_filter,
            limit=fetch_limit,
            offset=None,  # Qdrant offset is a cursor (PointId), not an integer
            with_payload=True,
        )
        return [self._record_to_result(r) for r in records[offset:]]

    async def delete(self, collection: str, ids: list[str]) -> None:
        """Delete points by their string IDs."""
        from qdrant_client.models import PointIdsList

        client = await self._ensure_client()
        int_ids = [self._str_to_point_id(sid) for sid in ids]
        await client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=int_ids),
        )

    async def delete_collection(self, collection: str) -> None:
        """Drop a Qdrant collection entirely."""
        client = await self._ensure_client()
        await client.delete_collection(collection)
        logger.info("QdrantAdapter: deleted collection '%s'", collection)

    async def count(self, collection: str) -> int:
        """Return the number of points in *collection*."""
        client = await self._ensure_client()
        result = await client.count(collection_name=collection)
        return result.count

    async def close(self) -> None:
        """Close the underlying Qdrant HTTP client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
            logger.debug("QdrantAdapter: connection closed")
