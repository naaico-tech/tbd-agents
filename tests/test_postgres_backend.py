"""Tests for the PostgreSQL backend: _translate_filters, PgQuerySet,
PostgresDocument, BeanieRepository, PostgresRepository, and deps.py DI.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.db_postgres import (
    PgQuerySet,
    PostgresDocument,
    _translate_filters,
)
from app.repositories.beanie_repo import BeanieRepository
from app.repositories.postgres_repo import PostgresRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tf(filters: dict, model_cls=None) -> tuple[str, dict]:
    """Call _translate_filters and return (sql_fragment, params)."""
    params: dict = {}
    sql = _translate_filters(model_cls, filters, params)
    return sql, params


# ---------------------------------------------------------------------------
# 1. _translate_filters — pure logic, no DB required
# ---------------------------------------------------------------------------


class TestTranslateFilters:
    """Unit tests for the MongoDB-style → JSONB WHERE-clause translator."""

    def test_empty_returns_true(self):
        """An empty filter dict should produce 'TRUE' (match everything)."""
        sql, params = _tf({})
        assert sql == "TRUE"
        assert params == {}

    def test_simple_equality(self):
        """A plain key=value pair should produce a direct column equality clause."""
        sql, params = _tf({"name": "alice"})
        assert "name" in sql
        assert "=" in sql
        assert len(params) == 1
        assert "alice" in params.values()

    def test_simple_equality_int(self):
        """Integer values should be passed through as-is (not coerced to str)."""
        sql, params = _tf({"score": 42})
        assert "score" in sql
        assert 42 in params.values()

    def test_simple_equality_bool(self):
        """Bool values should be passed through (not coerced to str)."""
        sql, params = _tf({"active": True})
        assert "active" in sql
        assert True in params.values()

    def test_none_value_is_null_check(self):
        """A None value should produce an IS NULL clause."""
        sql, params = _tf({"email": None})
        assert "IS NULL" in sql
        # No bind parameter needed for IS NULL
        assert params == {}

    def test_id_key_maps_to_primary_key(self):
        """Filtering by 'id' or '_id' should use the row's id column."""
        sql, params = _tf({"id": "abc-123"})
        assert "id = :" in sql
        assert "abc-123" in params.values()

    def test_underscore_id_maps_to_primary_key(self):
        """Filtering by '_id' should also map to the id column."""
        sql, params = _tf({"_id": "xyz-456"})
        assert "id = :" in sql
        assert "xyz-456" in params.values()

    def test_operator_in_nonempty(self):
        """$in with values should produce an IN (...) clause."""
        sql, params = _tf({"status": {"$in": ["active", "inactive"]}})
        assert "IN (" in sql
        assert "status" in sql
        assert "active" in params.values()
        assert "inactive" in params.values()

    def test_operator_in_empty_list_is_false(self):
        """$in with an empty list should short-circuit to FALSE."""
        sql, params = _tf({"status": {"$in": []}})
        assert sql == "FALSE"

    def test_operator_in_array_column_uses_any(self):
        """$in on a TEXT[] column should produce ANY(col) clauses, not IN (...)."""
        from app.db_postgres import ARRAY
        from sqlalchemy import TEXT

        class _FakeModel:
            @classmethod
            def _get_column_map(cls):
                return {"tags": ARRAY(TEXT())}

        sql, params = _tf({"tags": {"$in": ["sre", "jira"]}}, model_cls=_FakeModel)
        assert "IN (" not in sql
        assert "ANY(tags)" in sql
        assert "sre" in params.values()
        assert "jira" in params.values()

    def test_operator_ne(self):
        """$ne should produce a != clause."""
        sql, params = _tf({"status": {"$ne": "deleted"}})
        assert "!=" in sql
        assert "status" in sql

    def test_operator_lt_numeric(self):
        """$lt with a number should produce a < clause."""
        sql, params = _tf({"score": {"$lt": 10}})
        assert "score" in sql
        assert "< :" in sql
        assert 10 in params.values()

    def test_operator_gt_numeric(self):
        """$gt with a number should produce a > clause."""
        sql, params = _tf({"score": {"$gt": 0}})
        assert "score" in sql
        assert "> :" in sql
        assert 0 in params.values()

    def test_operator_lte_numeric(self):
        """$lte with a number should produce a <= clause."""
        sql, params = _tf({"score": {"$lte": 100}})
        assert "<=" in sql
        assert 100 in params.values()

    def test_operator_gte_numeric(self):
        """$gte with a number should produce a >= clause."""
        sql, params = _tf({"score": {"$gte": 1}})
        assert ">=" in sql
        assert 1 in params.values()

    def test_operator_lt_datetime(self):
        """$lt with a datetime should produce a < clause."""
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        sql, params = _tf({"created_at": {"$lt": dt}})
        assert "created_at" in sql
        assert "< :" in sql
        assert dt in params.values()

    def test_operator_gt_datetime(self):
        """$gt with a datetime should produce a > clause."""
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        sql, params = _tf({"created_at": {"$gt": dt}})
        assert "created_at" in sql
        assert "> :" in sql
        assert dt in params.values()

    def test_operator_lte_datetime(self):
        """$lte with a datetime should produce a <= clause."""
        dt = datetime(2024, 6, 15, tzinfo=UTC)
        sql, params = _tf({"updated_at": {"$lte": dt}})
        assert "updated_at" in sql
        assert "<=" in sql

    def test_operator_gte_datetime(self):
        """$gte with a datetime should produce a >= clause."""
        dt = datetime(2024, 6, 15, tzinfo=UTC)
        sql, params = _tf({"updated_at": {"$gte": dt}})
        assert "updated_at" in sql
        assert ">=" in sql

    def test_operator_exists_true(self):
        """$exists: True should produce an IS NOT NULL clause."""
        sql, params = _tf({"email": {"$exists": True}})
        assert "IS NOT NULL" in sql
        assert "email" in sql

    def test_operator_exists_false(self):
        """$exists: False should produce an IS NULL clause."""
        sql, params = _tf({"email": {"$exists": False}})
        assert "IS NULL" in sql
        assert "email" in sql

    def test_multiple_conditions_joined_by_and(self):
        """Multiple top-level keys should be ANDed together."""
        sql, params = _tf({"name": "bob", "active": True})
        assert " AND " in sql
        assert "name" in sql
        assert "active" in sql

    # ── dot-notation / JSONB sub-field tests ──────────────────────────────

    def test_dot_notation_scalar_equality(self):
        """metadata.workflow_id = 'abc' → metadata->>'workflow_id' = :p0."""
        sql, params = _tf({"metadata.workflow_id": "abc"})
        assert "metadata->>'workflow_id'" in sql
        assert "=" in sql
        assert "abc" in params.values()
        assert "metadata.workflow_id" not in sql  # must not appear verbatim

    def test_dot_notation_scalar_none(self):
        """metadata.workflow_id = None → metadata->'workflow_id' IS NULL."""
        sql, params = _tf({"metadata.workflow_id": None})
        assert "metadata->'workflow_id' IS NULL" in sql
        assert params == {}

    def test_dot_notation_in_uses_jsonb_contains(self):
        """metadata.tags $in ['sre', 'jira'] → uses JSONB ? operator per value."""
        sql, params = _tf({"metadata.tags": {"$in": ["sre", "jira"]}})
        # Must use jsonb ? operator, not IN (...)
        assert "IN (" not in sql
        assert "metadata->'tags' ?" in sql
        assert "sre" in params.values()
        assert "jira" in params.values()

    def test_dot_notation_in_empty_is_false(self):
        """metadata.tags $in [] → FALSE."""
        sql, params = _tf({"metadata.tags": {"$in": []}})
        assert sql == "FALSE"

    def test_dot_notation_ne(self):
        """metadata.status $ne 'deleted' → metadata->>'status' != :p0."""
        sql, params = _tf({"metadata.status": {"$ne": "deleted"}})
        assert "metadata->>'status'" in sql
        assert "!=" in sql
        assert "deleted" in params.values()

    def test_dot_notation_exists_true(self):
        """metadata.workflow_id $exists True → metadata->'workflow_id' IS NOT NULL."""
        sql, params = _tf({"metadata.workflow_id": {"$exists": True}})
        assert "metadata->'workflow_id' IS NOT NULL" in sql
        assert params == {}

    def test_dot_notation_exists_false(self):
        """metadata.workflow_id $exists False → metadata->'workflow_id' IS NULL."""
        sql, params = _tf({"metadata.workflow_id": {"$exists": False}})
        assert "metadata->'workflow_id' IS NULL" in sql
        assert params == {}

    def test_dot_notation_combined_with_top_level(self):
        """Dot-notation and regular keys can appear in the same filter."""
        sql, params = _tf({"agent_id": "a1", "metadata.workflow_id": "wf1"})
        assert "AND" in sql
        assert "agent_id" in sql
        assert "metadata->>'workflow_id'" in sql
        assert "a1" in params.values()
        assert "wf1" in params.values()

    def test_lt_gt_combined(self):
        """$lt and $gt on the same key should produce two separate conditions."""
        sql, params = _tf({"score": {"$lt": 10, "$gt": 0}})
        # Both comparisons should appear in the clause
        assert "<" in sql
        assert ">" in sql
        assert "score" in sql

    def test_param_idx_starts_from_existing_params(self):
        """If params already has entries, new params should not collide."""
        params: dict = {"p0": "existing"}
        _translate_filters(None, {"name": "alice"}, params)
        # p0 should still be "existing", new param should be p1
        assert params["p0"] == "existing"
        assert any(k != "p0" and v == "alice" for k, v in params.items())

    def test_non_primitive_value_coerced_to_list(self):
        """A list value with TEXT fallback type should be stored as a list."""
        sql, params = _tf({"tags": ["a", "b"]})
        assert "tags" in sql
        assert ["a", "b"] in params.values()


# ---------------------------------------------------------------------------
# 2. PgQuerySet — chainable query builder (no DB calls)
# ---------------------------------------------------------------------------


class TestPgQuerySet:
    """Tests for PgQuerySet chaining behaviour."""

    def _make_model_cls(self, table: str = "agents"):
        """Return a minimal mock model class with get_collection_name."""
        m = MagicMock()
        m.get_collection_name.return_value = table
        return m

    def test_initial_state(self):
        model = self._make_model_cls()
        qs = PgQuerySet(model, {"id": "1"})
        assert qs._limit_val is None
        assert qs._skip_val == 0
        assert qs._sort_fields == []

    def test_sort_returns_new_queryset(self):
        model = self._make_model_cls()
        qs = PgQuerySet(model)
        qs2 = qs.sort("+name")
        assert qs is not qs2
        assert qs2._sort_fields == ["+name"]
        # Original is unchanged
        assert qs._sort_fields == []

    def test_limit_returns_new_queryset(self):
        model = self._make_model_cls()
        qs = PgQuerySet(model)
        qs2 = qs.limit(20)
        assert qs is not qs2
        assert qs2._limit_val == 20
        assert qs._limit_val is None

    def test_skip_returns_new_queryset(self):
        model = self._make_model_cls()
        qs = PgQuerySet(model)
        qs2 = qs.skip(10)
        assert qs is not qs2
        assert qs2._skip_val == 10
        assert qs._skip_val == 0

    def test_sort_limit_skip_chain(self):
        model = self._make_model_cls()
        qs = PgQuerySet(model, {"id": "1"})
        qs2 = qs.sort("+name").limit(10).skip(5)
        assert qs2._limit_val == 10
        assert qs2._skip_val == 5
        assert qs2._sort_fields == ["+name"]

    def test_chain_preserves_filters(self):
        model = self._make_model_cls()
        filters = {"status": "active"}
        qs = PgQuerySet(model, filters).limit(5).skip(2)
        assert qs._filters == filters

    def test_build_query_basic_sql(self):
        """_build_query should include the table name and WHERE clause."""
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {})
        sql, params = qs._build_query()
        assert "agents" in sql
        assert "SELECT" in sql
        assert "WHERE" in sql

    def test_build_query_with_limit_and_skip(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {}).limit(5).skip(3)
        sql, params = qs._build_query()
        assert "LIMIT 5" in sql
        assert "OFFSET 3" in sql

    def test_build_query_no_offset_when_skip_zero(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {})
        sql, _ = qs._build_query()
        assert "OFFSET" not in sql

    def test_build_query_no_limit_when_not_set(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {})
        sql, _ = qs._build_query()
        assert "LIMIT" not in sql

    def test_build_query_sort_asc_plus_prefix(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {}).sort("+name")
        sql, _ = qs._build_query()
        assert "ASC" in sql
        assert "'name'" in sql or "name" in sql

    def test_build_query_sort_desc_minus_prefix(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {}).sort("-created_at")
        sql, _ = qs._build_query()
        assert "DESC" in sql

    def test_build_query_sort_created_at_no_data_prefix(self):
        """created_at is a column, not a JSON field — should not use data->."""
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {}).sort("-created_at")
        sql, _ = qs._build_query()
        # created_at should appear as a direct column reference in ORDER BY
        assert "created_at DESC" in sql

    def test_build_query_default_order_by_created_at(self):
        """Without explicit sort, should default to ORDER BY created_at DESC."""
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {})
        sql, _ = qs._build_query()
        assert "ORDER BY created_at DESC" in sql

    def test_build_query_with_filter_produces_param(self):
        model = self._make_model_cls("agents")
        qs = PgQuerySet(model, {"name": "alice"})
        sql, params = qs._build_query()
        assert "alice" in params.values()

    async def test_to_list_calls_session(self):
        """to_list should call the session and reconstruct model instances."""
        model = self._make_model_cls("agents")
        fake_row = MagicMock()
        fake_row._mapping = {"id": "id-1", "name": "alice"}
        model._from_row.return_value = fake_row

        mock_mappings = MagicMock()
        mock_mappings.fetchall.return_value = [fake_row]

        mock_result = MagicMock()
        mock_result.mappings.return_value = mock_mappings

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)):
            qs = PgQuerySet(model, {})
            result = await qs.to_list()

        assert result == [fake_row]
        mock_session.execute.assert_awaited_once()

    async def test_count_calls_session(self):
        """count() should issue a SELECT COUNT(*) and return an integer."""
        model = self._make_model_cls("agents")

        mock_result = MagicMock()
        mock_result.scalar.return_value = 7

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)):
            qs = PgQuerySet(model, {})
            count = await qs.count()

        assert count == 7


# ---------------------------------------------------------------------------
# 3. PostgresDocument instance helpers
# ---------------------------------------------------------------------------


class _FakeDoc(PostgresDocument):
    """Minimal concrete PostgresDocument subclass for testing."""

    class Settings:
        name = "fake_table"

    def __init__(self, id: str | None = None, name: str = ""):
        self.id = id
        self.name = name

    def model_dump(self, **kwargs):
        return {"name": self.name}

    def _to_data(self):
        return {"name": self.name}


class TestPostgresDocument:
    def test_get_collection_name(self):
        assert _FakeDoc.get_collection_name() == "fake_table"

    def test_from_row_with_dict_data(self):
        """_from_row should reconstruct an instance from (id, data_dict, ...)."""
        row = ("row-id-1", {"name": "alice"}, datetime.now(UTC), datetime.now(UTC))

        class _RowDoc(PostgresDocument):
            class Settings:
                name = "row_docs"

            def __init__(self, id=None, name=""):
                self.id = id
                self.name = name

            @classmethod
            def model_validate(cls, data):
                return cls(id=data.get("id"), name=data.get("name", ""))

        doc = _RowDoc._from_row(row)
        assert doc.id == "row-id-1"
        assert doc.name == "alice"

    def test_from_row_with_json_string_data(self):
        """_from_row should parse JSON string data."""
        import json

        row = ("row-id-2", json.dumps({"name": "bob"}), datetime.now(UTC), datetime.now(UTC))

        class _JsonDoc(PostgresDocument):
            class Settings:
                name = "json_docs"

            def __init__(self, id=None, name=""):
                self.id = id
                self.name = name

            @classmethod
            def model_validate(cls, data):
                return cls(id=data.get("id"), name=data.get("name", ""))

        doc = _JsonDoc._from_row(row)
        assert doc.name == "bob"
        assert doc.id == "row-id-2"

    def test_find_returns_pgqueryset(self):
        qs = _FakeDoc.find({"name": "test"})
        assert isinstance(qs, PgQuerySet)

    def test_find_all_returns_pgqueryset(self):
        qs = _FakeDoc.find_all()
        assert isinstance(qs, PgQuerySet)

    def test_find_with_kwargs_merges(self):
        """find() should merge positional dict conditions with keyword filters."""
        qs = _FakeDoc.find({"name": "test"}, status="active")
        assert qs._filters == {"name": "test", "status": "active"}

    async def test_save_generates_id_if_missing(self):
        """save() should assign a UUID if the document has no id."""
        doc = _FakeDoc(id=None, name="new-doc")

        mock_result = MagicMock()
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)):
            result = await doc.save()

        assert result is doc
        assert doc.id is not None
        mock_session.commit.assert_awaited_once()

    async def test_save_uses_existing_id(self):
        """save() should use the existing id if already set."""
        doc = _FakeDoc(id="existing-id-123", name="existing")

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)):
            await doc.save()

        # id should remain unchanged
        assert doc.id == "existing-id-123"
        call_params = mock_session.execute.call_args[0][1]
        assert call_params["id"] == "existing-id-123"

    async def test_delete_removes_document(self):
        """delete() should execute a DELETE statement with the doc's id."""
        doc = _FakeDoc(id="del-id-999", name="to-delete")

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_factory = MagicMock(return_value=mock_session)

        with patch("app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)):
            await doc.delete()

        mock_session.execute.assert_awaited_once()
        # Verify DELETE was issued for the right id
        call_params = mock_session.execute.call_args[0][1]
        assert call_params["id"] == "del-id-999"

    async def test_delete_raises_without_id(self):
        """delete() should raise ValueError when the document has an empty id."""
        # str(None) == "None" (truthy), so we need an empty string to trigger the guard
        doc = _FakeDoc(id="", name="orphan")

        with pytest.raises(ValueError, match="Cannot delete"):
            mock_session = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=False)
            mock_factory = MagicMock(return_value=mock_session)

            with patch(
                "app.db_postgres.get_session_factory", AsyncMock(return_value=mock_factory)
            ):
                await doc.delete()

    async def test_class_get_calls_find_one(self):
        """PostgresDocument.get() should delegate to find_one({'id': ...})."""
        mock_find_one = AsyncMock(return_value=None)
        with patch.object(_FakeDoc, "find_one", mock_find_one):
            result = await _FakeDoc.get("some-id")

        mock_find_one.assert_awaited_once_with({"id": "some-id"})
        assert result is None

    async def test_class_insert_calls_save(self):
        """PostgresDocument.insert() should call doc.save() and return it."""
        doc = _FakeDoc(id=None, name="insert-me")
        doc.save = AsyncMock(return_value=doc)

        result = await _FakeDoc.insert(doc)

        doc.save.assert_awaited_once()
        assert result is doc


# ---------------------------------------------------------------------------
# 4. BeanieRepository
# ---------------------------------------------------------------------------


class TestBeanieRepository:
    def _make_model(self):
        """Return a mock Beanie Document class."""
        model = MagicMock()
        model.get = AsyncMock(return_value=None)
        model.find_one = AsyncMock(return_value=None)
        qs = MagicMock()
        qs.to_list = AsyncMock(return_value=[])
        qs.count = AsyncMock(return_value=0)
        model.find.return_value = qs
        model.find_all.return_value = qs
        model.count = AsyncMock(return_value=0)
        model.insert = AsyncMock()
        return model, qs

    async def test_find_all_returns_empty_list(self):
        model, qs = self._make_model()
        repo = BeanieRepository(model)
        result = await repo.find_all()
        assert result == []
        model.find_all.assert_called_once()
        qs.to_list.assert_awaited_once()

    async def test_find_all_returns_documents(self):
        model, qs = self._make_model()
        fake_docs = [MagicMock(), MagicMock()]
        qs.to_list = AsyncMock(return_value=fake_docs)
        repo = BeanieRepository(model)
        result = await repo.find_all()
        assert result == fake_docs

    async def test_get_delegates_to_model_get(self):
        model, _ = self._make_model()
        fake_doc = MagicMock()
        model.get = AsyncMock(return_value=fake_doc)
        repo = BeanieRepository(model)
        result = await repo.get("doc-id-1")
        model.get.assert_awaited_once_with("doc-id-1")
        assert result is fake_doc

    async def test_get_returns_none_when_not_found(self):
        model, _ = self._make_model()
        model.get = AsyncMock(return_value=None)
        repo = BeanieRepository(model)
        assert await repo.get("missing-id") is None

    async def test_find_one_delegates_to_model(self):
        model, _ = self._make_model()
        fake_doc = MagicMock()
        model.find_one = AsyncMock(return_value=fake_doc)
        repo = BeanieRepository(model)
        result = await repo.find_one(name="alice")
        model.find_one.assert_awaited_once_with({"name": "alice"})
        assert result is fake_doc

    async def test_find_with_filters(self):
        model, qs = self._make_model()
        fake_docs = [MagicMock()]
        qs.to_list = AsyncMock(return_value=fake_docs)
        repo = BeanieRepository(model)
        result = await repo.find(status="active")
        model.find.assert_called_with({"status": "active"})
        assert result == fake_docs

    async def test_find_without_filters_uses_find_all(self):
        model, qs = self._make_model()
        repo = BeanieRepository(model)
        await repo.find()
        model.find_all.assert_called_once()

    async def test_save_calls_obj_save(self):
        model, _ = self._make_model()
        obj = MagicMock()
        obj.save = AsyncMock()
        repo = BeanieRepository(model)
        result = await repo.save(obj)
        obj.save.assert_awaited_once()
        assert result is obj

    async def test_insert_delegates_to_model_insert(self):
        model, _ = self._make_model()
        obj = MagicMock()
        obj.insert = AsyncMock(return_value=obj)
        repo = BeanieRepository(model)
        result = await repo.insert(obj)
        obj.insert.assert_awaited_once()
        assert result is obj

    async def test_delete_returns_true_when_found(self):
        model, _ = self._make_model()
        doc = MagicMock()
        doc.delete = AsyncMock()
        model.get = AsyncMock(return_value=doc)
        repo = BeanieRepository(model)
        result = await repo.delete("found-id")
        assert result is True
        doc.delete.assert_awaited_once()

    async def test_delete_returns_false_when_not_found(self):
        model, _ = self._make_model()
        model.get = AsyncMock(return_value=None)
        repo = BeanieRepository(model)
        result = await repo.delete("missing-id")
        assert result is False

    async def test_count_no_filters(self):
        model, _ = self._make_model()
        model.count = AsyncMock(return_value=5)
        repo = BeanieRepository(model)
        result = await repo.count()
        model.count.assert_awaited_once()
        assert result == 5

    async def test_count_with_filters(self):
        model, qs = self._make_model()
        qs.count = AsyncMock(return_value=3)
        repo = BeanieRepository(model)
        result = await repo.count(status="active")
        model.find.assert_called_with({"status": "active"})
        assert result == 3


# ---------------------------------------------------------------------------
# 5. PostgresRepository
# ---------------------------------------------------------------------------


class TestPostgresRepository:
    def _make_model(self):
        model = MagicMock()
        model.get = AsyncMock(return_value=None)
        model.find_one = AsyncMock(return_value=None)
        qs = MagicMock()
        qs.to_list = AsyncMock(return_value=[])
        qs.count = AsyncMock(return_value=0)
        model.find.return_value = qs
        model.insert = AsyncMock()
        return model, qs

    async def test_find_all_returns_empty_list(self):
        model, qs = self._make_model()
        repo = PostgresRepository(model)
        result = await repo.find_all()
        assert result == []
        model.find.assert_called_with({})
        qs.to_list.assert_awaited_once()

    async def test_find_all_returns_documents(self):
        model, qs = self._make_model()
        fake_docs = [MagicMock(), MagicMock()]
        qs.to_list = AsyncMock(return_value=fake_docs)
        repo = PostgresRepository(model)
        result = await repo.find_all()
        assert result == fake_docs

    async def test_get_delegates_to_model_get(self):
        model, _ = self._make_model()
        fake_doc = MagicMock()
        model.get = AsyncMock(return_value=fake_doc)
        repo = PostgresRepository(model)
        result = await repo.get("doc-id-2")
        model.get.assert_awaited_once_with("doc-id-2")
        assert result is fake_doc

    async def test_get_returns_none_when_not_found(self):
        model, _ = self._make_model()
        model.get = AsyncMock(return_value=None)
        repo = PostgresRepository(model)
        assert await repo.get("missing") is None

    async def test_find_one_delegates_to_model(self):
        model, _ = self._make_model()
        fake_doc = MagicMock()
        model.find_one = AsyncMock(return_value=fake_doc)
        repo = PostgresRepository(model)
        result = await repo.find_one(name="carol")
        model.find_one.assert_awaited_once_with({"name": "carol"})
        assert result is fake_doc

    async def test_find_with_filters(self):
        model, qs = self._make_model()
        fake_docs = [MagicMock()]
        qs.to_list = AsyncMock(return_value=fake_docs)
        repo = PostgresRepository(model)
        result = await repo.find(status="inactive")
        model.find.assert_called_with({"status": "inactive"})
        assert result == fake_docs

    async def test_find_without_filters_passes_empty_dict(self):
        model, qs = self._make_model()
        repo = PostgresRepository(model)
        await repo.find()
        model.find.assert_called_with({})

    async def test_save_calls_obj_save(self):
        model, _ = self._make_model()
        obj = MagicMock()
        obj.save = AsyncMock()
        repo = PostgresRepository(model)
        result = await repo.save(obj)
        obj.save.assert_awaited_once()
        assert result is obj

    async def test_insert_delegates_to_model_insert(self):
        model, _ = self._make_model()
        obj = MagicMock()
        obj.insert = AsyncMock(return_value=obj)
        repo = PostgresRepository(model)
        result = await repo.insert(obj)
        obj.insert.assert_awaited_once()
        assert result is obj

    async def test_delete_returns_true_when_found(self):
        model, _ = self._make_model()
        doc = MagicMock()
        doc.delete = AsyncMock()
        model.get = AsyncMock(return_value=doc)
        repo = PostgresRepository(model)
        result = await repo.delete("found-id")
        assert result is True
        doc.delete.assert_awaited_once()

    async def test_delete_returns_false_when_not_found(self):
        model, _ = self._make_model()
        model.get = AsyncMock(return_value=None)
        repo = PostgresRepository(model)
        result = await repo.delete("missing")
        assert result is False

    async def test_count_with_filters(self):
        model, qs = self._make_model()
        qs.count = AsyncMock(return_value=9)
        repo = PostgresRepository(model)
        result = await repo.count(status="active")
        model.find.assert_called_with({"status": "active"})
        assert result == 9

    async def test_count_without_filters(self):
        model, qs = self._make_model()
        qs.count = AsyncMock(return_value=42)
        repo = PostgresRepository(model)
        result = await repo.count()
        model.find.assert_called_with({})
        assert result == 42


# ---------------------------------------------------------------------------
# 6. Repository DI selection via deps.py
# ---------------------------------------------------------------------------


class TestDepsRepositorySelection:
    """Tests that get_*_repo() returns the correct backend.

    ``deps.py`` imports ``get_db_backend`` at module level via
    ``from app.db import get_db_backend``, so we must patch the name *inside*
    the ``app.repositories.deps`` namespace, not in ``app.db``.
    """

    def test_get_agent_repo_mongo(self):
        """When get_db_backend returns 'mongo', get_agent_repo returns BeanieRepository."""
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_agent_repo

            repo = get_agent_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_agent_repo_postgres(self):
        """When get_db_backend returns 'postgres', get_agent_repo returns PostgresRepository."""
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_agent_repo

            repo = get_agent_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_chat_session_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_chat_session_repo

            repo = get_chat_session_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_chat_session_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_chat_session_repo

            repo = get_chat_session_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_skill_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_skill_repo

            repo = get_skill_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_skill_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_skill_repo

            repo = get_skill_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_memory_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_memory_repo

            repo = get_memory_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_memory_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_memory_repo

            repo = get_memory_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_token_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_token_repo

            repo = get_token_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_token_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_token_repo

            repo = get_token_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_provider_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_provider_repo

            repo = get_provider_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_provider_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_provider_repo

            repo = get_provider_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_workflow_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_workflow_repo

            repo = get_workflow_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_workflow_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_workflow_repo

            repo = get_workflow_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_mcp_server_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_mcp_server_repo

            repo = get_mcp_server_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_mcp_server_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_mcp_server_repo

            repo = get_mcp_server_repo()
        assert isinstance(repo, PostgresRepository)

    def test_get_custom_tool_repo_mongo(self):
        with patch("app.repositories.deps.get_db_backend", return_value="mongo"):
            from app.repositories.deps import get_custom_tool_repo

            repo = get_custom_tool_repo()
        assert isinstance(repo, BeanieRepository)

    def test_get_custom_tool_repo_postgres(self):
        with patch("app.repositories.deps.get_db_backend", return_value="postgres"):
            from app.repositories.deps import get_custom_tool_repo

            repo = get_custom_tool_repo()
        assert isinstance(repo, PostgresRepository)


# ---------------------------------------------------------------------------
# 7. Dual-backend Agent model
# ---------------------------------------------------------------------------


class TestAgentModel:
    """Tests for the Agent model dual-backend pattern."""

    def test_agent_has_name_field(self):
        """Agent must have a 'name' field in its Pydantic model_fields."""
        from app.models.agent import Agent

        assert "name" in Agent.model_fields

    def test_agent_has_description_field(self):
        from app.models.agent import Agent

        assert "description" in Agent.model_fields

    def test_agent_has_system_prompt_field(self):
        from app.models.agent import Agent

        assert "system_prompt" in Agent.model_fields

    def test_agent_has_mcp_server_ids_field(self):
        from app.models.agent import Agent

        assert "mcp_server_ids" in Agent.model_fields

    def test_agent_settings_collection_name(self):
        """Agent.Settings.name should be 'agents'."""
        from app.models.agent import Agent

        assert Agent.Settings.name == "agents"

    def test_agent_default_db_is_mongo(self):
        """When DB_BACKEND is unset or 'mongo', Agent should NOT subclass PostgresDocument."""
        db_backend = os.environ.get("DB_BACKEND", "mongo").lower()
        if db_backend != "postgres":
            from app.models.agent import Agent

            assert not issubclass(Agent, PostgresDocument)

    def test_agent_instantiation_mongo_mode(self):
        """Agent can be imported and its class exists in mongo mode."""
        db_backend = os.environ.get("DB_BACKEND", "mongo").lower()
        if db_backend == "mongo":
            # In mongo mode Agent is a Beanie Document — skip instantiation
            # (requires Beanie initialisation), just verify the class exists.
            from app.models.agent import Agent

            assert Agent is not None

    def test_agent_postgres_mode_instantiation(self):
        """The Agent module exports the Agent class regardless of backend."""
        import app.models.agent as agent_mod

        assert hasattr(agent_mod, "Agent")


# ---------------------------------------------------------------------------
# 8. get_db_backend() from app.db
# ---------------------------------------------------------------------------


class TestGetDbBackend:
    def test_returns_mongo_by_default(self):
        """get_db_backend() should return 'mongo' when DB_BACKEND is not set."""
        with patch("app.db.settings") as mock_settings:
            mock_settings.db_backend = "mongo"
            from app.db import get_db_backend

            assert get_db_backend() == "mongo"

    def test_returns_postgres_when_configured(self):
        """get_db_backend() should return 'postgres' when so configured."""
        with patch("app.db.settings") as mock_settings:
            mock_settings.db_backend = "postgres"
            from app.db import get_db_backend

            assert get_db_backend() == "postgres"

    def test_is_callable(self):
        from app.db import get_db_backend

        assert callable(get_db_backend)
