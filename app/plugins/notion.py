"""Notion read/write plugin for tbd-agents.

Provides full read and write access to a Notion workspace via the
official ``notion-client`` library.  All seven operations are dispatched
through a single ``execute`` entry-point, keeping the tool surface compact
while covering the most important Notion API capabilities.

Supported operations
--------------------
Read:
    query_database   – Query a Notion database with optional filters/sorts.
    get_page         – Retrieve a page's properties and metadata.
    get_block_children – List child blocks of a page or block.
    search           – Full-text search across the workspace.

Write:
    create_page      – Create a new page in a database or under another page.
    update_page      – Update properties of an existing page.
    append_blocks    – Append block children to a page or block.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.plugin_base import PluginBase


class NotionPlugin(PluginBase):
    """Full read/write Notion workspace plugin.

    Uses the official ``notion-client`` Python SDK (imported lazily so the
    library is only required when the plugin is actually invoked).  The
    integration token is resolved from the ``NOTION_TOKEN`` environment
    variable, which is populated at runtime via the token manager reference
    ``{{token:notion-token}}``.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "notion"

    @property
    def description(self) -> str:
        return (
            "Read and write Notion workspace content: query databases, "
            "retrieve pages and blocks, search, create/update pages, "
            "and append block children."
        )

    @property
    def tags(self) -> list[str]:
        return ["notion", "knowledge", "pages", "databases"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"NOTION_TOKEN": "{{token:notion-token}}"}

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(  # noqa: PLR0912, PLR0911
        self,
        operation: str,
        database_id: str = "",
        page_id: str = "",
        block_id: str = "",
        query: str = "",
        filter: dict = None,  # noqa: A002  (shadows built-in intentionally for LLM clarity)
        sorts: list = None,
        properties: dict = None,
        children: list = None,
        title: str = "",
        content: str = "",
        start_cursor: str = "",
        page_size: int = 50,
    ) -> dict:
        """Execute a Notion API operation.

        Args:
            operation: One of ``query_database``, ``get_page``,
                ``get_block_children``, ``search``, ``create_page``,
                ``update_page``, ``append_blocks``.
            database_id: Notion database UUID.  Required for
                ``query_database`` and ``create_page`` (when creating inside
                a database).
            page_id: Notion page UUID.  Required for ``get_page``,
                ``update_page``, and ``create_page`` (when creating as a
                child of another page).
            block_id: Notion block or page UUID.  Required for
                ``get_block_children`` and ``append_blocks``.
            query: Search query string.  Required for ``search``.
            filter: Notion filter object passed to ``query_database``.
            sorts: Notion sorts list passed to ``query_database``.
            properties: Page property map for ``create_page`` (extra
                properties beyond the title) and ``update_page``.
            children: List of Notion block objects for ``create_page`` body
                and ``append_blocks``.
            title: Page title string used when constructing the ``Name``
                / ``title`` property for ``create_page``.
            content: Unused reserved field for future plain-text helpers.
            start_cursor: Pagination cursor returned by a previous call.
            page_size: Maximum number of items to return (capped at 100 for
                database/block endpoints, 20 for search).

        Returns:
            A JSON-serialisable dict whose keys depend on the operation.
            On error, returns ``{"error": "<message>"}``.
        """
        # ----------------------------------------------------------------
        # Lazy imports — notion-client is only required when the plugin runs
        # ----------------------------------------------------------------
        try:
            from notion_client import Client  # noqa: PLC0415
            from notion_client.errors import APIResponseError  # noqa: PLC0415
        except ImportError:
            return {
                "error": (
                    "The 'notion-client' package is not installed. "
                    "Install it with: pip install notion-client"
                )
            }

        # ----------------------------------------------------------------
        # Token validation
        # ----------------------------------------------------------------
        token = os.environ.get("NOTION_TOKEN")
        if not token:
            return {"error": "NOTION_TOKEN is not set in the environment."}

        client = Client(auth=token)
        op = operation.strip().lower()

        # ----------------------------------------------------------------
        # Dispatch
        # ----------------------------------------------------------------
        try:
            if op == "query_database":
                return self._query_database(
                    client, database_id, filter, sorts, start_cursor, page_size
                )
            if op == "get_page":
                return self._get_page(client, page_id)
            if op == "get_block_children":
                return self._get_block_children(
                    client, block_id, start_cursor, page_size
                )
            if op == "search":
                return self._search(client, query, page_size)
            if op == "create_page":
                return self._create_page(
                    client, database_id, page_id, title, properties, children
                )
            if op == "update_page":
                return self._update_page(client, page_id, properties)
            if op == "append_blocks":
                return self._append_blocks(client, block_id, children)

            return {"error": f"Unsupported operation: {operation!r}"}

        except APIResponseError as exc:
            return {"error": f"Notion API error ({exc.code}): {exc.body}"}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Private operation helpers
    # ------------------------------------------------------------------

    def _query_database(
        self,
        client: Any,
        database_id: str,
        filter: dict | None,  # noqa: A002
        sorts: list | None,
        start_cursor: str,
        page_size: int,
    ) -> dict:
        """Query a Notion database."""
        if not database_id:
            return {"error": "database_id is required for query_database."}

        kwargs: dict[str, Any] = {
            "database_id": database_id,
            "page_size": min(page_size, 100),
        }
        if filter:
            kwargs["filter"] = filter
        if sorts:
            kwargs["sorts"] = sorts
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = client.databases.query(**kwargs)
        return {
            "results": response.get("results", []),
            "has_more": response.get("has_more", False),
            "next_cursor": response.get("next_cursor"),
        }

    def _get_page(self, client: Any, page_id: str) -> dict:
        """Retrieve a Notion page's properties and metadata."""
        if not page_id:
            return {"error": "page_id is required for get_page."}

        return dict(client.pages.retrieve(page_id=page_id))

    def _get_block_children(
        self,
        client: Any,
        block_id: str,
        start_cursor: str,
        page_size: int,
    ) -> dict:
        """List child blocks of a page or block."""
        if not block_id:
            return {"error": "block_id is required for get_block_children."}

        kwargs: dict[str, Any] = {
            "block_id": block_id,
            "page_size": min(page_size, 100),
        }
        if start_cursor:
            kwargs["start_cursor"] = start_cursor

        response = client.blocks.children.list(**kwargs)
        return {
            "results": response.get("results", []),
            "has_more": response.get("has_more", False),
            "next_cursor": response.get("next_cursor"),
        }

    def _search(self, client: Any, query: str, page_size: int) -> dict:
        """Search across the Notion workspace."""
        if not query:
            return {"error": "query is required for search."}

        response = client.search(
            query=query,
            page_size=min(page_size, 20),
        )
        return {
            "results": response.get("results", []),
            "has_more": response.get("has_more", False),
            "next_cursor": response.get("next_cursor"),
        }

    def _create_page(
        self,
        client: Any,
        database_id: str,
        page_id: str,
        title: str,
        properties: dict | None,
        children: list | None,
    ) -> dict:
        """Create a new Notion page inside a database or under another page."""
        if not database_id and not page_id:
            return {
                "error": (
                    "Either database_id (to create inside a database) or "
                    "page_id (to create as a child page) is required for create_page."
                )
            }
        if not title:
            return {"error": "title is required for create_page."}

        # Build parent reference
        if database_id:
            parent: dict[str, str] = {"database_id": database_id}
            # Notion databases use "title" as the default title property key
            title_property_key = "title"
        else:
            parent = {"page_id": page_id}
            title_property_key = "title"

        # Compose properties — always include the title
        full_properties: dict[str, Any] = {
            title_property_key: {
                "title": [{"text": {"content": title}}]
            }
        }
        if properties:
            # Caller-supplied properties override/extend the defaults
            for key, value in properties.items():
                if key != title_property_key:
                    full_properties[key] = value

        response = client.pages.create(
            parent=parent,
            properties=full_properties,
            children=children or [],
        )
        return {
            "id": response.get("id"),
            "url": response.get("url"),
            "created_time": response.get("created_time"),
            "properties": response.get("properties"),
        }

    def _update_page(
        self,
        client: Any,
        page_id: str,
        properties: dict | None,
    ) -> dict:
        """Update properties of an existing Notion page."""
        if not page_id:
            return {"error": "page_id is required for update_page."}
        if not properties:
            return {"error": "properties dict is required for update_page."}

        response = client.pages.update(
            page_id=page_id,
            properties=properties,
        )
        return dict(response)

    def _append_blocks(
        self,
        client: Any,
        block_id: str,
        children: list | None,
    ) -> dict:
        """Append block children to a Notion page or block."""
        if not block_id:
            return {"error": "block_id is required for append_blocks."}
        if not children:
            return {"error": "children list is required for append_blocks."}

        response = client.blocks.children.append(
            block_id=block_id,
            children=children,
        )
        return {
            "results": response.get("results", []),
            "has_more": response.get("has_more", False),
        }
