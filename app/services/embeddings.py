"""Embeddings service backed by fastembed (local ONNX, no GPU required).

Provides a lazy-loaded singleton for generating text embeddings used by
semantic memory retrieval and knowledge search.  If fastembed is unavailable
or ``embeddings_enabled=False`` the service gracefully returns ``None`` so
callers can fall back to keyword/scroll retrieval without crashing.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import settings

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embeddings")


class EmbeddingsService:
    """Thin async wrapper around a fastembed TextEmbedding model.

    The model is loaded lazily on first use and cached for the lifetime of the
    process.  All CPU-bound operations are run in a thread executor to keep the
    FastAPI / Celery event loops unblocked.
    """

    def __init__(self) -> None:
        self._model = None
        self._init_lock = asyncio.Lock()
        self._failed = False  # permanent failure flag — stop retrying if init fails

    async def _ensure_loaded(self) -> bool:
        """Load the fastembed model if not already loaded.

        Returns ``True`` if the model is available, ``False`` otherwise.
        """
        if self._model is not None:
            return True
        if self._failed:
            return False
        if not settings.embeddings_enabled:
            return False

        async with self._init_lock:
            # Double-check after acquiring the lock
            if self._model is not None:
                return True
            if self._failed:
                return False

            try:
                loop = asyncio.get_event_loop()
                model = await loop.run_in_executor(
                    _executor, self._load_model, settings.embeddings_model
                )
                self._model = model
                logger.info(
                    "Embeddings model '%s' loaded (dim=%d)",
                    settings.embeddings_model,
                    settings.embeddings_dim,
                )
                return True
            except Exception as exc:
                self._failed = True
                logger.warning(
                    "Failed to load embeddings model '%s' — semantic retrieval disabled: %s",
                    settings.embeddings_model,
                    exc,
                )
                return False

    @staticmethod
    def _load_model(model_name: str):
        """Synchronous model load — called from thread executor."""
        from fastembed import TextEmbedding  # type: ignore[import]

        return TextEmbedding(model_name=model_name)

    @staticmethod
    def _run_embed(model, texts: list[str]) -> list[list[float]]:
        """Synchronous batch embed — called from thread executor."""
        return [vec.tolist() for vec in model.embed(texts)]

    async def embed_many(self, texts: list[str]) -> list[list[float]] | None:
        """Embed a batch of texts.

        Returns a list of float vectors, or ``None`` if embeddings are
        unavailable (model load failed or feature disabled).
        """
        if not texts:
            return []
        if not await self._ensure_loaded():
            return None
        try:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                _executor, self._run_embed, self._model, texts
            )
        except Exception as exc:
            logger.warning("embed_many failed: %s", exc)
            return None

    async def embed_one(self, text: str) -> list[float] | None:
        """Embed a single text string.

        Returns a float vector or ``None`` if embeddings are unavailable.
        """
        result = await self.embed_many([text])
        if result is None:
            return None
        return result[0] if result else None

    @property
    def is_available(self) -> bool:
        """Return True only if the model is currently loaded and ready."""
        return self._model is not None


embeddings_service = EmbeddingsService()
