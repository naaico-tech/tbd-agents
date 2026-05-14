"""PostgreSQL (JSONB) concrete repository implementation."""
from __future__ import annotations

from typing import Any, Generic, TypeVar

T = TypeVar("T")


class PostgresRepository(Generic[T]):
    """Wraps ``PostgresDocument`` API to satisfy the ``Repository[T]`` Protocol.

    Pass the ``PostgresDocument`` subclass (not an instance) as ``model``.
    All methods are ``async`` to match the Protocol signature.

    .. note::
        This module intentionally has **no** Beanie imports — the two
        implementations are kept fully independent.
    """

    def __init__(self, model: type[T]) -> None:
        self._model = model

    async def get(self, id: str) -> T | None:
        """Return a document by primary key, or ``None``."""
        return await self._model.get(id)  # type: ignore[attr-defined]

    async def find_one(self, **filters: Any) -> T | None:
        """Return the first document matching keyword *filters*, or ``None``."""
        return await self._model.find_one(filters)  # type: ignore[attr-defined]

    async def find(self, **filters: Any) -> list[T]:
        """Return all documents matching keyword *filters*."""
        return await self._model.find(filters or {}).to_list()  # type: ignore[attr-defined]

    async def find_all(self) -> list[T]:
        """Return every document in the table."""
        return await self._model.find({}).to_list()  # type: ignore[attr-defined]

    async def save(self, obj: T) -> T:
        """Persist (insert or update) *obj* and return the saved instance."""
        await obj.save()  # type: ignore[attr-defined]
        return obj

    async def insert(self, obj: T) -> T:
        """Insert *obj* as a new document and return it."""
        await obj.insert()  # type: ignore[attr-defined]
        return obj

    async def delete(self, id: str) -> bool:
        """Delete the document with *id*.  Returns ``True`` if found and deleted."""
        doc = await self.get(id)
        if doc is None:
            return False
        await doc.delete()  # type: ignore[attr-defined]
        return True

    async def count(self, **filters: Any) -> int:
        """Return the number of documents matching keyword *filters*."""
        return await self._model.find(filters or {}).count()  # type: ignore[attr-defined]
