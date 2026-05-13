"""Abstract repository base and concrete implementations."""
from __future__ import annotations

from typing import Any, Protocol, TypeVar

T = TypeVar("T")


class Repository(Protocol[T]):
    """Generic repository protocol for CRUD operations.

    All concrete repository implementations should satisfy this interface so
    that service-layer code can remain backend-agnostic (MongoDB *or*
    PostgreSQL).
    """

    async def get(self, id: str) -> T | None:
        """Return a single document by primary key, or ``None`` if not found."""
        ...

    async def find_one(self, **filters: Any) -> T | None:
        """Return the first document matching *filters*, or ``None``."""
        ...

    async def find(self, **filters: Any) -> list[T]:
        """Return all documents matching *filters*."""
        ...

    async def find_all(self) -> list[T]:
        """Return every document in the collection / table."""
        ...

    async def save(self, obj: T) -> T:
        """Persist (insert or update) *obj* and return the saved instance."""
        ...

    async def delete(self, id: str) -> bool:
        """Delete the document with the given *id*.

        Returns ``True`` if a document was deleted, ``False`` if not found.
        """
        ...

    async def count(self, **filters: Any) -> int:
        """Return the number of documents matching *filters*."""
        ...

    async def insert(self, obj: T) -> T:
        """Insert *obj* as a new document and return it."""
        ...
