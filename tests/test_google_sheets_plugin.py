"""Tests for app/plugins/google_sheets.py — GoogleSheetsPlugin."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.plugins.google_sheets import GoogleSheetsPlugin, _READ_OPS, _WRITE_OPS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def plugin():
    return GoogleSheetsPlugin()


def _mock_service():
    """Return a mock Sheets API service client."""
    return MagicMock()


def _patch_client(plugin, service):
    """Patch _get_client to return *service* and ensure HttpError is available."""
    target = "app.plugins.google_sheets.GoogleSheetsPlugin._get_client"
    return patch(target, return_value=service)


# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------


def test_plugin_name(plugin):
    assert plugin.name == "google_sheets"


def test_plugin_description_mentions_ops(plugin):
    desc = plugin.description
    assert "get_values" in desc
    assert "create_sheet" in desc
    assert "write_values" in desc


def test_plugin_tags(plugin):
    assert "google" in plugin.tags
    assert "sheets" in plugin.tags
    assert "write" in plugin.tags


def test_env_config(plugin):
    assert "GOOGLE_SHEETS_CREDENTIALS_JSON" in plugin.env_config


def test_op_sets_disjoint():
    assert _READ_OPS.isdisjoint(_WRITE_OPS), "READ_OPS and WRITE_OPS must not overlap"


# ---------------------------------------------------------------------------
# get_metadata
# ---------------------------------------------------------------------------


def test_get_metadata_success(plugin):
    service = _mock_service()
    service.spreadsheets().get().execute.return_value = {
        "spreadsheetId": "abc123",
        "spreadsheetProperties": {"title": "My Sheet", "locale": "en_US"},
        "sheets": [
            {"properties": {"title": "Sheet1"}},
            {"properties": {"title": "Sheet2"}},
        ],
    }
    with patch("app.plugins.google_sheets.GoogleSheetsPlugin._get_client", return_value=service):
        with patch("app.plugins.google_sheets.GoogleSheetsPlugin.execute", wraps=plugin.execute):
            # Import HttpError mock
            mock_http_error = type("HttpError", (Exception,), {})
            with patch.dict("sys.modules", {"googleapiclient.errors": MagicMock(HttpError=mock_http_error)}):
                pass

    # Direct call via _get_metadata
    service2 = MagicMock()
    service2.spreadsheets().get().execute.return_value = {
        "spreadsheetId": "abc123",
        "spreadsheetProperties": {"title": "My Sheet", "locale": "en_US"},
        "sheets": [
            {"properties": {"title": "Sheet1"}},
            {"properties": {"title": "Sheet2"}},
        ],
    }
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._get_metadata(service2, mock_http_error, "abc123")
    assert result["title"] == "My Sheet"
    assert result["locale"] == "en_US"
    assert result["sheets"] == ["Sheet1", "Sheet2"]
    assert result["spreadsheet_id"] == "abc123"


def test_get_metadata_http_error(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().get().execute.side_effect = mock_http_error("API Error")
    result = plugin._get_metadata(service, mock_http_error, "abc")
    assert "error" in result
    assert "Google Sheets API error" in result["error"]


# ---------------------------------------------------------------------------
# list_sheets
# ---------------------------------------------------------------------------


def test_list_sheets_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().get().execute.return_value = {
        "sheets": [
            {"properties": {"title": "Data", "sheetId": 0, "index": 0}},
            {"properties": {"title": "Summary", "sheetId": 1, "index": 1}},
        ]
    }
    result = plugin._list_sheets(service, mock_http_error, "abc123")
    assert len(result["sheets"]) == 2
    assert result["sheets"][0]["title"] == "Data"
    assert result["sheets"][1]["sheetId"] == 1


# ---------------------------------------------------------------------------
# get_values
# ---------------------------------------------------------------------------


def test_get_values_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().get().execute.return_value = {
        "range": "Sheet1!A1:C3",
        "values": [["Name", "Age", "Score"], ["Alice", "30", "95"], ["Bob", "25", "87"]],
    }
    result = plugin._get_values(service, mock_http_error, "abc", "Sheet1!A1:C3", "", 100)
    assert result["row_count"] == 3
    assert result["values"][0] == ["Name", "Age", "Score"]


def test_get_values_uses_sheet_name_fallback(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().get().execute.return_value = {
        "range": "Sheet1",
        "values": [["A"], ["B"]],
    }
    result = plugin._get_values(service, mock_http_error, "abc", "", "Sheet1", 100)
    assert result["row_count"] == 2


def test_get_values_no_range_error(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._get_values(service, mock_http_error, "abc", "", "", 100)
    assert "error" in result


def test_get_values_max_rows_clamped(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().get().execute.return_value = {
        "range": "Sheet1!A1:A5",
        "values": [["row1"], ["row2"], ["row3"], ["row4"], ["row5"]],
    }
    result = plugin._get_values(service, mock_http_error, "abc", "Sheet1!A1:A5", "", 2)
    assert result["row_count"] == 2


# ---------------------------------------------------------------------------
# create_sheet
# ---------------------------------------------------------------------------


def test_create_sheet_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().batchUpdate().execute.return_value = {
        "replies": [{"addSheet": {"properties": {"title": "Analysis - Test", "sheetId": 42}}}]
    }
    result = plugin._create_sheet(service, mock_http_error, "abc", "Analysis - Test")
    assert result["created"] is True
    assert result["sheet_title"] == "Analysis - Test"
    assert result["sheet_id"] == 42


def test_create_sheet_empty_title(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._create_sheet(service, mock_http_error, "abc", "")
    assert "error" in result


def test_create_sheet_http_error(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().batchUpdate().execute.side_effect = mock_http_error("already exists")
    result = plugin._create_sheet(service, mock_http_error, "abc", "MySheet")
    assert "error" in result


# ---------------------------------------------------------------------------
# write_values
# ---------------------------------------------------------------------------


def test_write_values_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().update().execute.return_value = {
        "updatedRange": "Analysis!A1:B3",
        "updatedRows": 3,
        "updatedColumns": 2,
        "updatedCells": 6,
    }
    rows = [["Header1", "Header2"], ["Val1", "Val2"], ["Val3", "Val4"]]
    result = plugin._write_values(service, mock_http_error, "abc", "Analysis!A1", rows, "USER_ENTERED")
    assert result["updated_rows"] == 3
    assert result["updated_cells"] == 6


def test_write_values_no_range(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._write_values(service, mock_http_error, "abc", "", [["A"]], "USER_ENTERED")
    assert "error" in result


def test_write_values_invalid_values_type(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._write_values(service, mock_http_error, "abc", "Sheet1!A1", "not-a-list", "USER_ENTERED")
    assert "error" in result


# ---------------------------------------------------------------------------
# append_values
# ---------------------------------------------------------------------------


def test_append_values_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().append().execute.return_value = {
        "updates": {"updatedRange": "Sheet1!A5:B6", "updatedRows": 2, "updatedCells": 4}
    }
    result = plugin._append_values(service, mock_http_error, "abc", "Sheet1!A1", [["x", "y"]], "USER_ENTERED")
    assert result["appended_rows"] == 2


def test_append_values_no_range(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._append_values(service, mock_http_error, "abc", "", [["x"]], "USER_ENTERED")
    assert "error" in result


# ---------------------------------------------------------------------------
# clear_range
# ---------------------------------------------------------------------------


def test_clear_range_success(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    service.spreadsheets().values().clear().execute.return_value = {}
    result = plugin._clear_range(service, mock_http_error, "abc", "Sheet1!A1:Z100")
    assert result["cleared"] is True
    assert result["range"] == "Sheet1!A1:Z100"


def test_clear_range_no_range(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    result = plugin._clear_range(service, mock_http_error, "abc", "")
    assert "error" in result


# ---------------------------------------------------------------------------
# execute() dispatch — missing googleapiclient package
# ---------------------------------------------------------------------------


def test_execute_unknown_operation(plugin):
    service = MagicMock()
    mock_http_error = type("HttpError", (Exception,), {})
    with patch("app.plugins.google_sheets.GoogleSheetsPlugin._get_client", return_value=service):
        import sys
        # Provide a fake googleapiclient.errors module
        fake_errors = MagicMock()
        fake_errors.HttpError = mock_http_error
        with patch.dict(sys.modules, {"googleapiclient.errors": fake_errors}):
            result = plugin.execute(
                operation="nonexistent_op",
                spreadsheet_id="abc123",
            )
    assert "error" in result
    assert "nonexistent_op" in result["error"]
