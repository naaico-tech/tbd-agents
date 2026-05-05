"""Full Google Sheets plugin for tbd-agents (read + write).

Extends the read-only ``google_sheets_read`` plugin with write operations so
that an LLM agent can both read data from an existing spreadsheet AND write
analysis results into a newly created sheet tab.

Operations
----------
Read:
  - ``get_values``    – read cell values from a range.
  - ``list_sheets``   – list all sheet tabs.
  - ``get_metadata``  – return spreadsheet title, locale and sheet names.

Write:
  - ``create_sheet``    – add a new sheet tab to an existing spreadsheet.
  - ``write_values``    – write a 2-D array of values to a range.
  - ``append_values``   – append rows after the last row of data in a range.
  - ``clear_range``     – clear all values in a range.

Authentication
--------------
Identical to BigQuery: set ``GOOGLE_SHEETS_CREDENTIALS_JSON`` to the JSON
string of a Google service-account key file.  The service account must have
**Editor** access to any spreadsheet you want to write to.
"""

from __future__ import annotations

import json
import os

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Full (read + write) scope — required for write operations.
_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_MAX_ROWS_HARD_LIMIT = 2000
_READ_OPS = {"get_values", "list_sheets", "get_metadata"}
_WRITE_OPS = {"create_sheet", "write_values", "append_values", "clear_range"}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class GoogleSheetsPlugin(PluginBase):
    """Google Sheets plugin with full read and write access.

    Designed to power the *Google Sheets Analyst* agent, which reads data from
    a spreadsheet, analyses it, and writes insights to a new sheet tab.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "google_sheets"

    @property
    def description(self) -> str:
        return (
            "Full read/write access to Google Sheets. "
            "Read operations: get_values (read cell data), list_sheets (list tabs), "
            "get_metadata (spreadsheet info). "
            "Write operations: create_sheet (add new tab), write_values (write cells), "
            "append_values (append rows), clear_range (clear cells). "
            "All write operations require the service account to have Editor access."
        )

    @property
    def tags(self) -> list[str]:
        return ["google", "sheets", "spreadsheet", "read", "write", "analyst"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"GOOGLE_SHEETS_CREDENTIALS_JSON": "{{token:google-sheets-credentials}}"}

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _get_client(self):
        """Build an authenticated Sheets v4 API client.

        Uses ``GOOGLE_SHEETS_CREDENTIALS_JSON`` (a JSON string of a Google
        service-account key) with the full spreadsheets scope so both reads
        and writes are permitted.
        """
        from google.oauth2.service_account import Credentials  # noqa: PLC0415
        from googleapiclient.discovery import build  # noqa: PLC0415

        creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "").strip()
        if not creds_json:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS_JSON environment variable is not set.")

        credentials = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=_SCOPES,
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    # ------------------------------------------------------------------
    # Main entrypoint
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        spreadsheet_id: str,
        # --- read params ---
        range: str = "",
        sheet_name: str = "",
        max_rows: int = 100,
        # --- write params ---
        title: str = "",
        values: list | None = None,
        value_input_option: str = "USER_ENTERED",
    ) -> dict:
        """Execute a Google Sheets operation.

        Args:
            operation: One of the supported operations (see module docstring).
            spreadsheet_id: The spreadsheet ID from the Google Sheets URL.
            range: A1-notation range (e.g. ``"Sheet1!A1:D10"``).
                   Required for ``get_values``, ``write_values``,
                   ``append_values``, and ``clear_range``.
            sheet_name: Alternative to *range* for ``get_values`` — just the
                        tab name.
            max_rows: Maximum rows returned by ``get_values`` (clamped 1–2000).
            title: New sheet tab title for ``create_sheet``.
            values: 2-D list (rows → cells) for ``write_values`` and
                    ``append_values``.  E.g. ``[["Name","Score"],["Alice",95]]``.
            value_input_option: ``"USER_ENTERED"`` (default, parses formulas)
                                 or ``"RAW"`` (literal strings).

        Returns:
            A dict with operation-specific keys on success, or
            ``{"error": "<message>"}`` on failure.
        """
        try:
            from googleapiclient.errors import HttpError  # noqa: PLC0415
        except ImportError as exc:
            return {"error": f"Required package not installed: {exc}."}

        try:
            service = self._get_client()
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return {"error": str(exc)}

        op = operation.strip().lower()

        # ── Read operations ────────────────────────────────────────────
        if op == "get_values":
            return self._get_values(service, HttpError, spreadsheet_id, range, sheet_name, max_rows)

        if op == "list_sheets":
            return self._list_sheets(service, HttpError, spreadsheet_id)

        if op == "get_metadata":
            return self._get_metadata(service, HttpError, spreadsheet_id)

        # ── Write operations ───────────────────────────────────────────
        if op == "create_sheet":
            return self._create_sheet(service, HttpError, spreadsheet_id, title)

        if op == "write_values":
            return self._write_values(service, HttpError, spreadsheet_id, range, values or [], value_input_option)

        if op == "append_values":
            return self._append_values(service, HttpError, spreadsheet_id, range, values or [], value_input_option)

        if op == "clear_range":
            return self._clear_range(service, HttpError, spreadsheet_id, range)

        all_ops = sorted(_READ_OPS | _WRITE_OPS)
        return {"error": f"Unsupported operation: {operation!r}. Choose from: {', '.join(all_ops)}."}

    # ------------------------------------------------------------------
    # Read handlers
    # ------------------------------------------------------------------

    def _get_values(self, service, HttpError, spreadsheet_id, range_notation, sheet_name, max_rows) -> dict:
        effective_range = range_notation.strip() or sheet_name.strip()
        if not effective_range:
            return {"error": "get_values requires 'range' (e.g. 'Sheet1!A1:D10') or 'sheet_name'."}

        bounded = max(1, min(max_rows, _MAX_ROWS_HARD_LIMIT))
        try:
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=effective_range)
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error: {exc}"}

        all_values: list[list] = result.get("values", [])
        return {
            "values": all_values[:bounded],
            "range": result.get("range", effective_range),
            "row_count": len(all_values[:bounded]),
        }

    def _list_sheets(self, service, HttpError, spreadsheet_id) -> dict:
        try:
            result = (
                service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error: {exc}"}

        sheets = [
            {
                "title": s["properties"].get("title", ""),
                "sheetId": s["properties"].get("sheetId"),
                "index": s["properties"].get("index"),
            }
            for s in result.get("sheets", [])
        ]
        return {"sheets": sheets}

    def _get_metadata(self, service, HttpError, spreadsheet_id) -> dict:
        try:
            result = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error: {exc}"}

        props: dict = result.get("spreadsheetProperties", {})
        sheet_names = [s["properties"].get("title", "") for s in result.get("sheets", [])]
        return {
            "spreadsheet_id": result.get("spreadsheetId", spreadsheet_id),
            "title": props.get("title", ""),
            "locale": props.get("locale", ""),
            "sheets": sheet_names,
        }

    # ------------------------------------------------------------------
    # Write handlers
    # ------------------------------------------------------------------

    def _create_sheet(self, service, HttpError, spreadsheet_id, title) -> dict:
        """Add a new tab named *title* to the spreadsheet."""
        if not title.strip():
            return {"error": "create_sheet requires a non-empty 'title'."}

        body = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {"title": title.strip()}
                    }
                }
            ]
        }
        try:
            result = (
                service.spreadsheets()
                .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error creating sheet: {exc}"}

        reply = result.get("replies", [{}])[0]
        new_sheet = reply.get("addSheet", {}).get("properties", {})
        return {
            "created": True,
            "sheet_title": new_sheet.get("title", title),
            "sheet_id": new_sheet.get("sheetId"),
        }

    def _write_values(
        self, service, HttpError, spreadsheet_id, range_notation, values, value_input_option
    ) -> dict:
        """Write a 2-D array of values to *range_notation*."""
        if not range_notation.strip():
            return {"error": "write_values requires a non-empty 'range' (e.g. 'Analysis!A1')."}
        if not isinstance(values, list):
            return {"error": "write_values requires 'values' to be a list of lists."}

        body = {"values": values}
        try:
            result = (
                service.spreadsheets()
                .values()
                .update(
                    spreadsheetId=spreadsheet_id,
                    range=range_notation.strip(),
                    valueInputOption=value_input_option,
                    body=body,
                )
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error writing values: {exc}"}

        return {
            "updated_range": result.get("updatedRange"),
            "updated_rows": result.get("updatedRows", 0),
            "updated_columns": result.get("updatedColumns", 0),
            "updated_cells": result.get("updatedCells", 0),
        }

    def _append_values(
        self, service, HttpError, spreadsheet_id, range_notation, values, value_input_option
    ) -> dict:
        """Append *values* after the last row of data in *range_notation*."""
        if not range_notation.strip():
            return {"error": "append_values requires a non-empty 'range'."}
        if not isinstance(values, list):
            return {"error": "append_values requires 'values' to be a list of lists."}

        body = {"values": values}
        try:
            result = (
                service.spreadsheets()
                .values()
                .append(
                    spreadsheetId=spreadsheet_id,
                    range=range_notation.strip(),
                    valueInputOption=value_input_option,
                    insertDataOption="INSERT_ROWS",
                    body=body,
                )
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error appending values: {exc}"}

        updates = result.get("updates", {})
        return {
            "appended_range": updates.get("updatedRange"),
            "appended_rows": updates.get("updatedRows", 0),
            "appended_cells": updates.get("updatedCells", 0),
        }

    def _clear_range(self, service, HttpError, spreadsheet_id, range_notation) -> dict:
        """Clear all values in *range_notation*."""
        if not range_notation.strip():
            return {"error": "clear_range requires a non-empty 'range'."}

        try:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_notation.strip(),
                body={},
            ).execute()
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error clearing range: {exc}"}

        return {"cleared": True, "range": range_notation.strip()}
