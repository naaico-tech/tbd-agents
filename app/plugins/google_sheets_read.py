"""Read-only Google Sheets plugin for tbd-agents.

Provides three operations against the Google Sheets API v4:
- ``get_values``   – read cell values from a named range.
- ``list_sheets``  – list all sheet tabs in a spreadsheet.
- ``get_metadata`` – return title, locale, and sheet names for a spreadsheet.

Credentials are supplied via the ``GOOGLE_SHEETS_CREDENTIALS_JSON`` environment
variable as a JSON string of a Google service-account key file — the same
format used by the BigQuery plugin (``BIGQUERY_CREDENTIALS_JSON``).  The
``google-auth`` and ``google-api-python-client`` packages are imported lazily
inside :meth:`GoogleSheetsReadPlugin._get_client` so the plugin module can be
imported even when those packages are not installed.
"""

from __future__ import annotations

import json
import os

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
_MAX_ROWS_HARD_LIMIT = 1000


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class GoogleSheetsReadPlugin(PluginBase):
    """Read-only Google Sheets plugin.

    Allows an LLM agent to read data from Google Sheets using a service-account
    credential stored in the ``GOOGLE_SHEETS_CREDENTIALS`` environment variable.
    All three operations are strictly read-only; no writes are performed.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "google_sheets_read"

    @property
    def description(self) -> str:
        return (
            "Read-only access to Google Sheets. "
            "Supports reading cell values from a named range, "
            "listing all sheet tabs, and fetching spreadsheet metadata."
        )

    @property
    def tags(self) -> list[str]:
        return ["google", "sheets", "read-only", "spreadsheet"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"GOOGLE_SHEETS_CREDENTIALS_JSON": "{{token:google-sheets-credentials}}"}

    # ------------------------------------------------------------------
    # Internal helper — mirrors BigQuery's _get_client pattern
    # ------------------------------------------------------------------

    def _get_client(self):
        """Build and return an authenticated Sheets API service client.

        Reads ``GOOGLE_SHEETS_CREDENTIALS_JSON`` from the environment (a JSON
        string of a Google service-account key file) and constructs credentials
        with the spreadsheets read-only scope — identical to how
        ``BigqueryReadPlugin._get_client`` works with
        ``BIGQUERY_CREDENTIALS_JSON``.

        Returns:
            A ``googleapiclient`` Resource for the Sheets v4 API.

        Raises:
            ValueError: If the env var is missing or contains invalid JSON.
            Exception: Propagated from credential construction or API build.
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
        range: str = "",
        sheet_name: str = "",
        max_rows: int = 100,
    ) -> dict:
        """Execute a read-only Google Sheets operation.

        Args:
            operation: One of ``"get_values"``, ``"list_sheets"``, or
                ``"get_metadata"``.
            spreadsheet_id: The unique identifier of the target Google
                spreadsheet (the long alphanumeric string in the sheet URL).
            range: A1-notation range string, e.g. ``"Sheet1!A1:D10"``.
                Required for ``get_values``.  When only a sheet name is needed
                you may also pass it here or use *sheet_name*.
            sheet_name: Optional sheet/tab name used to construct a default
                range for ``get_values`` when *range* is not provided.
            max_rows: Maximum number of rows to return for ``get_values``.
                Clamped to 1 – 1000.

        Returns:
            A dict whose shape depends on the operation:

            * ``get_values`` → ``{"values": [...], "range": "...", "row_count": N}``
            * ``list_sheets`` → ``{"sheets": [{"title": ..., "sheetId": ..., "index": ...}, ...]}``
            * ``get_metadata`` → ``{"spreadsheet_id": ..., "title": ..., "locale": ..., "sheets": [...]}``
            * On any error → ``{"error": "<message>"}``
        """
        try:
            from googleapiclient.errors import HttpError  # noqa: PLC0415
        except ImportError as exc:
            return {
                "error": (
                    f"Required package not installed: {exc}. "
                    "Install google-auth and google-api-python-client."
                )
            }

        try:
            service = self._get_client()
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return {"error": str(exc)}

        # ----------------------------------------------------------------
        # Dispatch to the requested operation
        # ----------------------------------------------------------------
        operation_name = operation.strip().lower()

        if operation_name == "get_values":
            return self._get_values(service, HttpError, spreadsheet_id, range, sheet_name, max_rows)

        if operation_name == "list_sheets":
            return self._list_sheets(service, HttpError, spreadsheet_id)

        if operation_name == "get_metadata":
            return self._get_metadata(service, HttpError, spreadsheet_id)

        return {"error": f"Unsupported operation: {operation!r}. Choose from: get_values, list_sheets, get_metadata."}

    # ------------------------------------------------------------------
    # Private operation handlers
    # ------------------------------------------------------------------

    def _get_values(
        self,
        service,
        HttpError,
        spreadsheet_id: str,
        range_notation: str,
        sheet_name: str,
        max_rows: int,
    ) -> dict:
        """Read cell values from the spreadsheet.

        Args:
            service: Authenticated Sheets API client.
            HttpError: The ``googleapiclient.errors.HttpError`` class (passed
                in to avoid a second lazy import).
            spreadsheet_id: Target spreadsheet ID.
            range_notation: A1-notation range, e.g. ``"Sheet1!A1:D10"``.
            sheet_name: Fallback sheet name used when *range_notation* is empty.
            max_rows: Maximum number of rows to return (clamped to 1–1000).

        Returns:
            ``{"values": [...], "range": "...", "row_count": N}`` on success,
            or ``{"error": "..."}`` on failure.
        """
        effective_range = range_notation.strip() or sheet_name.strip()
        if not effective_range:
            return {"error": "get_values requires 'range' (e.g. 'Sheet1!A1:D10') or 'sheet_name'."}

        bounded_max_rows = max(1, min(max_rows, _MAX_ROWS_HARD_LIMIT))

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
            return {"error": f"Unexpected error calling get values: {exc}"}

        all_values: list[list] = result.get("values", [])
        truncated_values = all_values[:bounded_max_rows]

        return {
            "values": truncated_values,
            "range": result.get("range", effective_range),
            "row_count": len(truncated_values),
        }

    def _list_sheets(self, service, HttpError, spreadsheet_id: str) -> dict:
        """List all sheets/tabs in a spreadsheet.

        Args:
            service: Authenticated Sheets API client.
            HttpError: The ``googleapiclient.errors.HttpError`` class.
            spreadsheet_id: Target spreadsheet ID.

        Returns:
            ``{"sheets": [{"title": ..., "sheetId": ..., "index": ...}, ...]}``
            on success, or ``{"error": "..."}`` on failure.
        """
        try:
            result = (
                service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error listing sheets: {exc}"}

        sheets = [
            {
                "title": s["properties"].get("title", ""),
                "sheetId": s["properties"].get("sheetId"),
                "index": s["properties"].get("index"),
            }
            for s in result.get("sheets", [])
        ]

        return {"sheets": sheets}

    def _get_metadata(self, service, HttpError, spreadsheet_id: str) -> dict:
        """Return high-level spreadsheet metadata.

        Args:
            service: Authenticated Sheets API client.
            HttpError: The ``googleapiclient.errors.HttpError`` class.
            spreadsheet_id: Target spreadsheet ID.

        Returns:
            ``{"spreadsheet_id": ..., "title": ..., "locale": ..., "sheets": [...]}``
            on success, or ``{"error": "..."}`` on failure.
        """
        try:
            result = (
                service.spreadsheets()
                .get(spreadsheetId=spreadsheet_id)
                .execute()
            )
        except HttpError as exc:
            return {"error": f"Google Sheets API error: {exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error fetching metadata: {exc}"}

        spreadsheet_properties: dict = result.get("spreadsheetProperties", {})
        sheet_names: list[str] = [
            s["properties"].get("title", "")
            for s in result.get("sheets", [])
        ]

        return {
            "spreadsheet_id": result.get("spreadsheetId", spreadsheet_id),
            "title": spreadsheet_properties.get("title", ""),
            "locale": spreadsheet_properties.get("locale", ""),
            "sheets": sheet_names,
        }
