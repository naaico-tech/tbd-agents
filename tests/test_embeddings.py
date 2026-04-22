"""Tests for app.services.embeddings."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestEmbeddingsService:
    """Unit tests for EmbeddingsService — model load is always mocked."""

    def _make_service(self, model=None):
        """Return a fresh EmbeddingsService with embeddings_enabled=True."""
        from app.services.embeddings import EmbeddingsService

        svc = EmbeddingsService()
        if model is not None:
            svc._model = model
        return svc

    @pytest.mark.asyncio
    async def test_embed_one_returns_vector_when_model_loaded(self):
        fake_model = MagicMock()
        import numpy as np

        fake_model.embed.return_value = iter([np.array([0.1, 0.2, 0.3])])
        svc = self._make_service(model=fake_model)

        result = await svc.embed_one("hello world")
        assert isinstance(result, list)
        assert len(result) == 3
        assert abs(result[0] - 0.1) < 1e-6

    @pytest.mark.asyncio
    async def test_embed_many_returns_list_of_vectors(self):
        fake_model = MagicMock()
        import numpy as np

        fake_model.embed.return_value = iter([
            np.array([0.1, 0.2]),
            np.array([0.3, 0.4]),
        ])
        svc = self._make_service(model=fake_model)

        result = await svc.embed_many(["hello", "world"])
        assert len(result) == 2
        assert result[0] == pytest.approx([0.1, 0.2], abs=1e-6)
        assert result[1] == pytest.approx([0.3, 0.4], abs=1e-6)

    @pytest.mark.asyncio
    async def test_embed_many_empty_returns_empty_list(self):
        svc = self._make_service()
        result = await svc.embed_many([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_one_returns_none_when_model_failed(self):
        svc = self._make_service()
        svc._failed = True
        result = await svc.embed_one("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_one_returns_none_when_disabled(self):
        from app.services.embeddings import EmbeddingsService

        svc = EmbeddingsService()
        with patch("app.services.embeddings.settings") as mock_settings:
            mock_settings.embeddings_enabled = False
            result = await svc.embed_one("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_embed_many_returns_none_on_exception(self):
        fake_model = MagicMock()
        fake_model.embed.side_effect = RuntimeError("embed failed")
        svc = self._make_service(model=fake_model)

        result = await svc.embed_many(["hello"])
        assert result is None

    def test_is_available_false_when_model_not_loaded(self):
        svc = self._make_service()
        assert svc.is_available is False

    def test_is_available_true_when_model_loaded(self):
        svc = self._make_service(model=MagicMock())
        assert svc.is_available is True
