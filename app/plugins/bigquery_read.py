"""Read-only Google BigQuery plugin for tbd-agents.

Provides four operations against BigQuery using a service-account JSON key:
- ``run_query``    — execute a read-only SELECT / WITH…SELECT statement
- ``list_datasets`` — enumerate datasets in a GCP project
- ``list_tables``  — enumerate tables in a dataset
- ``get_schema``   — retrieve column names and types for a table
"""

from app.core.plugin_base import PluginBase


class BigqueryReadPlugin(PluginBase):
    """Read-only BigQuery plugin for Google Cloud analytics workloads.

    All database-modifying statements are rejected before any network call is
    made.  Only SELECT and WITH…SELECT queries are allowed through
    ``run_query``.  Credentials are loaded from the ``BIGQUERY_CREDENTIALS_JSON``
    environment variable (a JSON-encoded service-account key), scoped to the
    ``bigquery.readonly`` OAuth2 scope so even a leaked token cannot mutate data.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "bigquery_read"

    @property
    def description(self) -> str:
        return (
            "Read-only Google BigQuery access: run SELECT queries, list datasets "
            "and tables, and inspect table schemas."
        )

    @property
    def tags(self) -> list[str]:
        return ["google", "bigquery", "read-only", "analytics"]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "BIGQUERY_CREDENTIALS_JSON": "{{token:bigquery-credentials}}",
            "BIGQUERY_PROJECT_ID": "{{token:bigquery-project}}",
        }

    # ------------------------------------------------------------------
    # SQL safety helpers — allowlist-based read-only enforcement
    # (adapted from mysql_read.py for BigQuery SQL dialect)
    # ------------------------------------------------------------------

    def _strip_leading_sql_comments(self, query: str) -> str:
        """Return *query* with any leading SQL comments removed."""
        i, length = 0, len(query)
        while i < length:
            while i < length and query[i].isspace():
                i += 1
            if query.startswith("--", i):
                end = query.find("\n", i)
                i = length if end == -1 else end + 1
            elif query.startswith("#", i):
                end = query.find("\n", i)
                i = length if end == -1 else end + 1
            elif query.startswith("/*", i):
                end = query.find("*/", i + 2)
                i = length if end == -1 else end + 2
            else:
                break
        return query[i:]

    def _has_multiple_statements(self, query: str) -> bool:
        """Return True if *query* contains more than one SQL statement."""
        in_single = in_double = in_backtick = False
        in_line_comment = in_block_comment = False
        i, length = 0, len(query)
        while i < length:
            ch = query[i]
            nxt = query[i + 1] if i + 1 < length else ""
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
            elif in_block_comment:
                if ch == "*" and nxt == "/":
                    in_block_comment = False
                    i += 1
            elif in_single:
                if ch == "'" and (i == 0 or query[i - 1] != "\\"):
                    in_single = False
            elif in_double:
                if ch == '"' and (i == 0 or query[i - 1] != "\\"):
                    in_double = False
            elif in_backtick:
                if ch == "`":
                    in_backtick = False
            elif ch == "-" and nxt == "-":
                in_line_comment = True
                i += 1
            elif ch == "#":
                in_line_comment = True
            elif ch == "/" and nxt == "*":
                in_block_comment = True
                i += 1
            elif ch == "'":
                in_single = True
            elif ch == '"':
                in_double = True
            elif ch == "`":
                in_backtick = True
            elif ch == ";":
                remainder = self._strip_leading_sql_comments(query[i + 1:]).strip()
                return bool(remainder)
            i += 1
        return False

    def _is_read_only_query(self, query: str) -> bool:
        """Return True only for allowlisted read-only BigQuery statements.

        Permits bare ``SELECT`` statements and ``WITH … SELECT`` CTEs.
        Rejects everything else (INSERT, UPDATE, DELETE, MERGE, DDL, etc.).
        Multi-statement inputs (semicolon-separated) are always rejected.
        """
        stripped = self._strip_leading_sql_comments(query).strip()
        if not stripped:
            return False
        if self._has_multiple_statements(stripped):
            return False
        upper = stripped.upper()
        # Plain SELECT
        read_only_prefixes = (
            "SELECT ",
            "SELECT\t",
            "SELECT\n",
        )
        if any(upper.startswith(p) for p in read_only_prefixes):
            return True
        # Bare SELECT (no trailing whitespace — entire query is just "SELECT")
        if upper == "SELECT":
            return True
        # WITH … SELECT (CTE): find the last ')' that closes the final CTE
        # definition (returns paren depth to 0), then verify the following
        # keyword is SELECT.
        if upper.startswith("WITH ") or upper.startswith("WITH\t") or upper.startswith("WITH\n"):
            depth = 0
            i = 4
            length = len(stripped)
            in_single = in_double = in_backtick = False
            last_close_pos = -1
            while i < length:
                ch = stripped[i]
                if in_single:
                    if ch == "'" and (i == 0 or stripped[i - 1] != "\\"):
                        in_single = False
                elif in_double:
                    if ch == '"' and (i == 0 or stripped[i - 1] != "\\"):
                        in_double = False
                elif in_backtick:
                    if ch == "`":
                        in_backtick = False
                elif ch == "'":
                    in_single = True
                elif ch == '"':
                    in_double = True
                elif ch == "`":
                    in_backtick = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        last_close_pos = i + 1
                i += 1

            if last_close_pos != -1:
                tail = self._strip_leading_sql_comments(
                    stripped[last_close_pos:]
                ).strip()
                tail_upper = tail.upper()
                return (
                    tail_upper == "SELECT"
                    or tail_upper.startswith("SELECT ")
                    or tail_upper.startswith("SELECT\t")
                    or tail_upper.startswith("SELECT\n")
                )
        return False

    # ------------------------------------------------------------------
    # Client builder helper
    # ------------------------------------------------------------------

    def _build_client(self, project_id: str):  # type: ignore[return]
        """Construct and return an authenticated, read-only BigQuery client.

        Args:
            project_id: GCP project to bill and scope the client to.

        Returns:
            A ``google.cloud.bigquery.Client`` instance.

        Raises:
            KeyError / ValueError: propagated from JSON parsing or credential
                construction — callers should wrap in try/except.
        """
        import json  # noqa: PLC0415
        import os  # noqa: PLC0415

        from google.cloud import bigquery  # noqa: PLC0415
        from google.oauth2 import service_account  # noqa: PLC0415

        creds_json = os.environ.get("BIGQUERY_CREDENTIALS_JSON")
        if not creds_json:
            raise ValueError("BIGQUERY_CREDENTIALS_JSON environment variable is not set.")

        creds = service_account.Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=["https://www.googleapis.com/auth/bigquery.readonly"],
        )
        return bigquery.Client(project=project_id, credentials=creds)

    def _resolve_project_id(self, project_id: str) -> str:
        """Return *project_id* if non-empty, else fall back to env var."""
        import os  # noqa: PLC0415

        resolved = project_id or os.environ.get("BIGQUERY_PROJECT_ID", "")
        if not resolved:
            raise ValueError(
                "project_id was not provided and BIGQUERY_PROJECT_ID is not set."
            )
        return resolved

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def execute(  # type: ignore[override]
        self,
        operation: str,
        query: str = "",
        project_id: str = "",
        dataset_id: str = "",
        table_id: str = "",
        max_rows: int = 100,
    ) -> dict:
        """Dispatch a read-only BigQuery operation.

        Args:
            operation:  One of ``run_query``, ``list_datasets``,
                        ``list_tables``, ``get_schema``.
            query:      SQL text for ``run_query``.  Must be a SELECT or
                        WITH…SELECT statement; all other statements are rejected.
            project_id: GCP project ID.  Falls back to the
                        ``BIGQUERY_PROJECT_ID`` environment variable when empty.
            dataset_id: BigQuery dataset ID.  Required for ``list_tables`` and
                        ``get_schema``.
            table_id:   BigQuery table ID.  Required for ``get_schema``.
            max_rows:   Maximum number of rows returned by ``run_query``
                        (clamped to 1 000).

        Returns:
            A dict whose shape depends on the operation:

            * ``run_query``     → ``{"rows": [...], "row_count": N, "schema": [...]}``
            * ``list_datasets`` → ``{"datasets": [...], "project_id": "..."}``
            * ``list_tables``   → ``{"tables": [...], "dataset_id": "..."}``
            * ``get_schema``    → ``{"table": "...", "schema": [...]}``
            * Any error        → ``{"error": "..."}``
        """
        max_rows = min(int(max_rows), 1000)

        dispatch = {
            "run_query": self._run_query,
            "list_datasets": self._list_datasets,
            "list_tables": self._list_tables,
            "get_schema": self._get_schema,
        }

        handler = dispatch.get(operation)
        if handler is None:
            return {
                "error": (
                    f"Unknown operation {operation!r}. "
                    f"Supported operations: {', '.join(dispatch)}"
                )
            }

        try:
            return handler(
                query=query,
                project_id=project_id,
                dataset_id=dataset_id,
                table_id=table_id,
                max_rows=max_rows,
            )
        except Exception as exc:
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Operation implementations
    # ------------------------------------------------------------------

    def _run_query(
        self,
        query: str,
        project_id: str,
        dataset_id: str,
        table_id: str,
        max_rows: int,
    ) -> dict:
        """Execute a read-only SELECT / WITH…SELECT query and return rows."""
        if not query:
            return {"error": "The 'query' parameter is required for run_query."}
        if not self._is_read_only_query(query):
            return {
                "error": (
                    "Only read-only SELECT (or WITH…SELECT) queries are permitted. "
                    "Data-modifying and DDL statements are blocked."
                )
            }

        project_id = self._resolve_project_id(project_id)
        client = self._build_client(project_id)

        query_job = client.query(query)
        results = query_job.result(max_results=max_rows)

        rows = [dict(row) for row in results]
        schema = [
            {"name": field.name, "type": field.field_type}
            for field in results.schema
        ]
        return {"rows": rows, "row_count": len(rows), "schema": schema}

    def _list_datasets(
        self,
        query: str,
        project_id: str,
        dataset_id: str,
        table_id: str,
        max_rows: int,
    ) -> dict:
        """List all datasets visible in *project_id*."""
        project_id = self._resolve_project_id(project_id)
        client = self._build_client(project_id)

        datasets = list(client.list_datasets(project=project_id))
        return {
            "datasets": [d.dataset_id for d in datasets],
            "project_id": project_id,
        }

    def _list_tables(
        self,
        query: str,
        project_id: str,
        dataset_id: str,
        table_id: str,
        max_rows: int,
    ) -> dict:
        """List all tables (and views) in *dataset_id*."""
        if not dataset_id:
            return {"error": "The 'dataset_id' parameter is required for list_tables."}

        project_id = self._resolve_project_id(project_id)
        client = self._build_client(project_id)

        tables = list(client.list_tables(dataset_id))
        return {
            "tables": [
                {"table_id": t.table_id, "type": t.table_type}
                for t in tables
            ],
            "dataset_id": dataset_id,
        }

    def _get_schema(
        self,
        query: str,
        project_id: str,
        dataset_id: str,
        table_id: str,
        max_rows: int,
    ) -> dict:
        """Return the schema (column names and types) for *dataset_id.table_id*."""
        if not dataset_id:
            return {"error": "The 'dataset_id' parameter is required for get_schema."}
        if not table_id:
            return {"error": "The 'table_id' parameter is required for get_schema."}

        project_id = self._resolve_project_id(project_id)
        client = self._build_client(project_id)

        table = client.get_table(f"{dataset_id}.{table_id}")
        schema = [
            {
                "name": field.name,
                "type": field.field_type,
                "mode": field.mode,
                "description": field.description or "",
            }
            for field in table.schema
        ]
        return {
            "table": f"{project_id}.{dataset_id}.{table_id}",
            "schema": schema,
        }
