"""
Tests for the vector store abstraction layer.
Covers: factory routing, singleton behaviour, ABC contract on both adapters.
All external I/O (asyncpg, qdrant-client) is mocked.
"""

from unittest.mock import patch

import pytest

from app.services.vector_store import (
    AbstractVectorStore,
    SearchResult,
    VectorPoint,
    VectorStoreBackend,
    get_vector_store,
    reset_vector_store,
)
from app.services.vector_store.pgvector_adapter import PgvectorAdapter
from app.services.vector_store.qdrant_adapter import QdrantAdapter

# ── Factory Tests ─────────────────────────────────────────────────────────────


class TestGetVectorStore:
    """Tests for the get_vector_store() factory function and its singleton behaviour."""

    def setup_method(self):
        """Reset singleton before each test for isolation."""
        reset_vector_store()

    def teardown_method(self):
        """Reset singleton after each test to avoid cross-test contamination."""
        reset_vector_store()

    def test_returns_none_when_qdrant_backend_no_url(self):
        """When qdrant backend is selected but qdrant_url is None, returns None."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "qdrant"
            mock_settings.qdrant_url = None
            result = get_vector_store()
        assert result is None

    def test_returns_qdrant_adapter_when_configured(self):
        """When qdrant backend is configured with a URL, returns a QdrantAdapter."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "qdrant"
            mock_settings.qdrant_url = "http://localhost:6333"
            mock_settings.qdrant_api_key = None
            result = get_vector_store()
        assert isinstance(result, QdrantAdapter)

    def test_returns_none_when_pgvector_backend_no_dsn(self):
        """When pgvector backend is selected but pgvector_dsn is None, returns None."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "pgvector"
            mock_settings.pgvector_dsn = None
            result = get_vector_store()
        assert result is None

    def test_returns_pgvector_adapter_when_configured(self):
        """When pgvector backend has a DSN configured, returns a PgvectorAdapter."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "pgvector"
            mock_settings.pgvector_dsn = "postgresql+asyncpg://user:pass@localhost:5432/db"
            mock_settings.pgvector_table_prefix = "vs"
            result = get_vector_store()
        assert isinstance(result, PgvectorAdapter)

    def test_singleton_returns_same_instance(self):
        """Calling get_vector_store() twice returns the exact same object."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "pgvector"
            mock_settings.pgvector_dsn = "postgresql+asyncpg://user:pass@localhost:5432/db"
            mock_settings.pgvector_table_prefix = "vs"
            instance1 = get_vector_store()
            instance2 = get_vector_store()
        assert instance1 is instance2

    def test_reset_clears_singleton(self):
        """After reset_vector_store(), the next call returns a fresh instance."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "pgvector"
            mock_settings.pgvector_dsn = "postgresql+asyncpg://user:pass@localhost:5432/db"
            mock_settings.pgvector_table_prefix = "vs"
            instance1 = get_vector_store()
            reset_vector_store()
            instance2 = get_vector_store()
        assert instance1 is not instance2

    def test_qdrant_adapter_receives_api_key(self):
        """QdrantAdapter is initialised with the configured api_key."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "qdrant"
            mock_settings.qdrant_url = "http://localhost:6333"
            mock_settings.qdrant_api_key = "secret-key"
            result = get_vector_store()
        assert isinstance(result, QdrantAdapter)
        assert result._api_key == "secret-key"

    def test_pgvector_adapter_receives_table_prefix(self):
        """PgvectorAdapter is initialised with the configured table prefix."""
        with patch("app.services.vector_store.factory.settings") as mock_settings:
            mock_settings.vector_store_backend = "pgvector"
            mock_settings.pgvector_dsn = "postgresql+asyncpg://user:pass@localhost:5432/db"
            mock_settings.pgvector_table_prefix = "myapp"
            result = get_vector_store()
        assert isinstance(result, PgvectorAdapter)
        assert result._table_prefix == "myapp"


# ── ABC Contract Tests ────────────────────────────────────────────────────────


class TestAbstractVectorStoreContract:
    """Tests that verify both adapters fully implement AbstractVectorStore."""

    ABSTRACT_METHODS = [
        "create_collection",
        "collection_exists",
        "upsert",
        "search",
        "scroll",
        "delete",
        "delete_collection",
        "count",
        "close",
    ]

    @pytest.mark.parametrize("adapter_class", [QdrantAdapter, PgvectorAdapter])
    def test_all_abstract_methods_implemented(self, adapter_class):
        """Each adapter must define all abstract methods from AbstractVectorStore."""
        for method_name in self.ABSTRACT_METHODS:
            assert hasattr(adapter_class, method_name), (
                f"{adapter_class.__name__} is missing abstract method '{method_name}'"
            )
            assert callable(getattr(adapter_class, method_name)), (
                f"{adapter_class.__name__}.{method_name} is not callable"
            )

    @pytest.mark.parametrize("adapter_class", [QdrantAdapter, PgvectorAdapter])
    def test_adapter_is_subclass_of_abstract(self, adapter_class):
        """Both adapters must be concrete subclasses of AbstractVectorStore."""
        assert issubclass(adapter_class, AbstractVectorStore)

    @pytest.mark.parametrize("adapter_class", [QdrantAdapter, PgvectorAdapter])
    def test_adapter_is_instantiable_without_error(self, adapter_class):
        """Both adapters can be instantiated without raising (no network I/O in __init__)."""
        if adapter_class is QdrantAdapter:
            instance = adapter_class(url="http://localhost:6333")
        else:
            instance = adapter_class(dsn="postgresql://localhost/testdb")
        assert instance is not None

    def test_abstract_base_cannot_be_instantiated(self):
        """AbstractVectorStore cannot be instantiated directly (it has abstract methods)."""
        with pytest.raises(TypeError):
            AbstractVectorStore()  # type: ignore[abstract]


# ── Dataclass Tests ───────────────────────────────────────────────────────────


class TestDataclasses:
    """Tests for VectorPoint and SearchResult dataclasses."""

    def test_vector_point_defaults(self):
        """VectorPoint payload defaults to empty dict when not provided."""
        point = VectorPoint(id="test-id", vector=[0.1, 0.2, 0.3])
        assert point.id == "test-id"
        assert point.vector == [0.1, 0.2, 0.3]
        assert point.payload == {}

    def test_vector_point_with_payload(self):
        """VectorPoint stores a custom payload dict."""
        point = VectorPoint(id="p1", vector=[0.5, 0.6], payload={"agent": "a1", "key": "fact"})
        assert point.payload == {"agent": "a1", "key": "fact"}

    def test_vector_point_payload_is_independent_per_instance(self):
        """Each VectorPoint gets its own default payload dict (no shared mutable state)."""
        p1 = VectorPoint(id="p1", vector=[0.1])
        p2 = VectorPoint(id="p2", vector=[0.2])
        p1.payload["x"] = 1
        assert "x" not in p2.payload

    def test_search_result_fields(self):
        """SearchResult id, score, and payload are accessible and correct."""
        result = SearchResult(id="r1", score=0.95, payload={"k": "v"})
        assert result.id == "r1"
        assert result.score == 0.95
        assert result.payload == {"k": "v"}

    def test_search_result_defaults(self):
        """SearchResult payload defaults to empty dict when omitted."""
        result = SearchResult(id="r1", score=0.0)
        assert result.payload == {}

    def test_search_result_score_zero_for_scroll(self):
        """Scroll results conventionally have score=0.0."""
        result = SearchResult(id="r2", score=0.0, payload={"key": "test"})
        assert result.score == 0.0

    def test_vector_store_backend_enum_values(self):
        """VectorStoreBackend has expected string values."""
        assert VectorStoreBackend.QDRANT == "qdrant"
        assert VectorStoreBackend.PGVECTOR == "pgvector"

    def test_vector_store_backend_is_str(self):
        """VectorStoreBackend members are string-comparable."""
        assert VectorStoreBackend.QDRANT == "qdrant"
        assert str(VectorStoreBackend.PGVECTOR) == "pgvector"
