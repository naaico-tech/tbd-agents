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

    def execute(self, query: str, max_rows: int = 50) -> dict:
        """Execute a read-only SELECT query against the MySQL database."""
        import os
        import pymysql

        # Block destructive SQL
        dangerous_keywords = ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
        if any(query.strip().upper().startswith(kw) for kw in dangerous_keywords):
            return {"error": "Write operations are not allowed. Only SELECT queries permitted."}

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
