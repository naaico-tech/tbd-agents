"""MySQL read-only query plugin for tbd-agents."""

from app.core.plugin_base import PluginBase


class MysqlReadPlugin(PluginBase):
    @property
    def name(self) -> str:
        return "mysql_read"

    @property
    def description(self) -> str:
        return "Read-only MySQL database access for querying user metrics and logs."

    @property
    def tags(self) -> list[str]:
        return ["database", "mysql"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"MYSQL_CONNECTION": "{{token:mysql-readonly-conn}}"}

    # ------------------------------------------------------------------
    # SQL safety helpers — allowlist-based read-only enforcement
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

    def _first_keyword(self, query: str) -> str:
        """Return the uppercased first keyword token of *query*.

        Strips leading SQL comments before extracting the token.
        """
        stripped = self._strip_leading_sql_comments(query).strip()
        if not stripped:
            return ""
        token_chars = []
        for ch in stripped:
            if ch.isalpha() or ch == "_":
                token_chars.append(ch.upper())
            else:
                break
        return "".join(token_chars)

    def _is_read_only_query(self, query: str) -> bool:
        """Return True only for allowlisted read-only statements."""
        stripped = self._strip_leading_sql_comments(query).strip()
        if not stripped:
            return False
        if self._has_multiple_statements(stripped):
            return False
        upper = stripped.upper()
        read_only_prefixes = ("SELECT ", "SELECT\t", "SELECT\n",
                              "SHOW ", "SHOW\t", "SHOW\n",
                              "DESCRIBE ", "DESCRIBE\t", "DESC ",
                              "EXPLAIN ", "EXPLAIN\t", "EXPLAIN\n")
        if any(upper.startswith(p) for p in read_only_prefixes):
            return True
        # WITH ... SELECT (CTE): scan to find the last ')' that closes the final
        # CTE definition (returns depth to 0), then check the main verb that follows.
        if upper.startswith("WITH ") or upper.startswith("WITH\t") or upper.startswith("WITH\n"):
            depth = 0
            i = 4
            length = len(stripped)
            in_single = in_double = in_backtick = False
            last_close_pos = -1  # index just after the ')' that returns depth to 0
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

    def execute(self, query: str, max_rows: int = 50) -> dict:
        """Execute a read-only SELECT query against the MySQL database."""
        import os  # noqa: PLC0415

        import pymysql  # noqa: PLC0415

        if not self._is_read_only_query(query):
            return {"error": "Only read-only SELECT queries are permitted."}

        conn_string = os.environ.get("MYSQL_CONNECTION")
        if not conn_string:
            return {"error": "Database credentials not found in environment."}

        try:
            creds, host_db = conn_string.replace("mysql+pymysql://", "").split("@")
            user, pwd = creds.split(":")
            host_port, db = host_db.split("/")
            if ":" in host_port:
                host, port = host_port.split(":")
                port = int(port)
            else:
                host = host_port
                port = 3306
        except ValueError:
            return {"error": "Invalid MYSQL_CONNECTION format. Expected mysql+pymysql://user:pass@host:port/db"}

        try:
            connection = pymysql.connect(
                host=host,
                user=user,
                password=pwd,
                database=db,
                port=port,
                cursorclass=pymysql.cursors.DictCursor,
                connect_timeout=5,
            )
            with connection.cursor() as cursor:
                cursor.execute(query)
                results = cursor.fetchmany(max_rows)
            return {"results": results, "row_count": len(results)}
        except Exception as exc:
            return {"error": str(exc)}
        finally:
            if "connection" in locals() and connection.open:
                connection.close()
