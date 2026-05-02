"""SlackReaderPlugin — read-only Slack messaging plugin for tbd-agents.

Provides access to public Slack channels, message history, thread replies,
and keyword search without any write operations.

Required Slack bot token scopes:
  - channels:read      (list_channels, get_channel_info)
  - channels:history   (get_channel_history, get_thread_replies)
  - search:read        (search_messages — requires user token, not bot token)

The token is resolved at runtime via the ``SLACK_BOT_TOKEN`` environment
variable, which is populated from the ``{{token:slack-bot-token}}`` secret.
"""

from __future__ import annotations

import os

from app.core.plugin_base import PluginBase

#: Maximum number of results that can be requested in a single call.
_MAX_LIMIT = 200


class SlackReaderPlugin(PluginBase):
    """Read-only Slack plugin that surfaces channels, messages, threads, and search.

    All operations are strictly non-destructive — no messages are sent, no
    channels are modified, and no reactions are posted.  The plugin delegates
    all API calls to the official ``slack-sdk`` ``WebClient``, which is
    imported lazily inside :meth:`execute` so that the dependency is only
    required at invocation time.

    Supported operations
    --------------------
    ``list_channels``
        List public channels the bot has access to.
    ``get_channel_history``
        Fetch recent messages from a channel (by id or name).
    ``get_thread_replies``
        Fetch all replies in a message thread.
    ``search_messages``
        Search messages by keyword across the workspace.
    ``get_channel_info``
        Get metadata for a specific channel.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "slack_reader"

    @property
    def description(self) -> str:
        return (
            "Read-only Slack access: list channels, fetch message history, "
            "read thread replies, search by keyword, and get channel details. "
            "Never sends messages or modifies any Slack data."
        )

    @property
    def tags(self) -> list[str]:
        return ["slack", "messaging", "read-only", "communication"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"SLACK_BOT_TOKEN": "{{token:slack-bot-token}}"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):  # type: ignore[return]
        """Build and return a configured ``WebClient``.

        Imports ``slack_sdk`` lazily so the module is only required when the
        plugin is actually invoked.

        Returns:
            A ``slack_sdk.WebClient`` instance authenticated with the bot token.

        Raises:
            RuntimeError: If ``SLACK_BOT_TOKEN`` is not set in the environment.
        """
        from slack_sdk import WebClient  # noqa: PLC0415

        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise RuntimeError("SLACK_BOT_TOKEN is not set in the environment.")
        return WebClient(token=token)

    def _resolve_channel_id(self, client, channel_name: str, limit: int) -> str | None:
        """Resolve a channel name to its Slack channel ID.

        Iterates through ``list_channels`` pages until a match is found or
        all pages are exhausted.

        Args:
            client: An authenticated ``WebClient`` instance.
            channel_name: The human-readable channel name (with or without ``#``).
            limit: Page size to use when listing channels.

        Returns:
            The channel ID string, or ``None`` if no match was found.
        """
        from slack_sdk.errors import SlackApiError  # noqa: PLC0415

        name_clean = channel_name.lstrip("#").lower()
        cursor: str | None = None

        while True:
            try:
                response = client.conversations_list(
                    types="public_channel",
                    limit=min(limit, _MAX_LIMIT),
                    cursor=cursor or None,
                )
            except SlackApiError:
                return None

            for channel in response.get("channels", []):
                if channel.get("name", "").lower() == name_clean:
                    return channel["id"]

            next_cursor = (
                response.get("response_metadata", {}).get("next_cursor") or ""
            )
            if not next_cursor:
                break
            cursor = next_cursor

        return None

    # ------------------------------------------------------------------
    # execute
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        channel_id: str = "",
        channel_name: str = "",
        thread_ts: str = "",
        query: str = "",
        limit: int = 50,
        cursor: str = "",
    ) -> dict:
        """Perform a read-only Slack operation.

        Args:
            operation: One of ``list_channels``, ``get_channel_history``,
                ``get_thread_replies``, ``search_messages``, or
                ``get_channel_info``.
            channel_id: Slack channel ID (e.g. ``C01234ABCDE``).  Required for
                ``get_channel_history`` (unless ``channel_name`` is given),
                ``get_thread_replies``, and ``get_channel_info``.
            channel_name: Human-readable channel name (e.g. ``general`` or
                ``#general``).  Used as a fallback for ``get_channel_history``
                when ``channel_id`` is not supplied — the name is resolved to
                an ID via ``list_channels``.
            thread_ts: The timestamp of the parent message (as returned by the
                Slack API, e.g. ``1715000000.000100``).  Required for
                ``get_thread_replies``.
            query: Keyword query string.  Required for ``search_messages``.
            limit: Maximum number of items to return (clamped to 1–200).
                Defaults to ``50``.
            cursor: Pagination cursor returned by a previous API call.  Pass
                this to retrieve the next page of results for
                ``list_channels`` and ``get_channel_history``.

        Returns:
            A dict whose structure depends on the operation:

            * ``list_channels`` → ``{"channels": [...], "next_cursor": "..."}``
            * ``get_channel_history`` → ``{"messages": [...], "channel_id": "..."}``
            * ``get_thread_replies`` → ``{"replies": [...], "channel_id": "...", "thread_ts": "..."}``
            * ``search_messages`` → ``{"matches": [...], "total": int, "query": "..."}``
            * ``get_channel_info`` → ``{"channel": {...}}``
            * On error → ``{"error": "..."}``
        """
        from slack_sdk.errors import SlackApiError  # noqa: PLC0415

        # Clamp limit to a safe range.
        bounded_limit = max(1, min(limit, _MAX_LIMIT))
        op = operation.strip().lower()

        # Acquire client — propagate missing-token as an error dict.
        try:
            client = self._get_client()
        except RuntimeError as exc:
            return {"error": str(exc)}

        # ----------------------------------------------------------------
        # list_channels
        # ----------------------------------------------------------------
        if op == "list_channels":
            try:
                response = client.conversations_list(
                    types="public_channel",
                    limit=bounded_limit,
                    cursor=cursor or None,
                )
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            channels = [
                {
                    "id": ch.get("id", ""),
                    "name": ch.get("name", ""),
                    "topic": ch.get("topic", {}).get("value", ""),
                    "num_members": ch.get("num_members", 0),
                    "is_private": ch.get("is_private", False),
                }
                for ch in response.get("channels", [])
            ]
            next_cursor = (
                response.get("response_metadata", {}).get("next_cursor") or ""
            )
            return {"channels": channels, "next_cursor": next_cursor}

        # ----------------------------------------------------------------
        # get_channel_history
        # ----------------------------------------------------------------
        if op == "get_channel_history":
            resolved_id = channel_id.strip()

            # Resolve channel name to ID when only a name is supplied.
            if not resolved_id and channel_name:
                resolved_id = self._resolve_channel_id(
                    client, channel_name, bounded_limit
                ) or ""

            if not resolved_id:
                return {
                    "error": (
                        "channel_id or channel_name is required for get_channel_history."
                    )
                }

            try:
                response = client.conversations_history(
                    channel=resolved_id,
                    limit=bounded_limit,
                )
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            messages = [
                {
                    "ts": msg.get("ts", ""),
                    "text": msg.get("text", ""),
                    "user": msg.get("user", ""),
                    "thread_ts": msg.get("thread_ts", ""),
                    "reply_count": msg.get("reply_count", 0),
                }
                for msg in response.get("messages", [])
            ]
            return {"messages": messages, "channel_id": resolved_id}

        # ----------------------------------------------------------------
        # get_thread_replies
        # ----------------------------------------------------------------
        if op == "get_thread_replies":
            if not channel_id.strip():
                return {"error": "channel_id is required for get_thread_replies."}
            if not thread_ts.strip():
                return {"error": "thread_ts is required for get_thread_replies."}

            try:
                response = client.conversations_replies(
                    channel=channel_id.strip(),
                    ts=thread_ts.strip(),
                    limit=bounded_limit,
                )
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            replies = [
                {
                    "ts": msg.get("ts", ""),
                    "text": msg.get("text", ""),
                    "user": msg.get("user", ""),
                    "thread_ts": msg.get("thread_ts", ""),
                    "reply_count": msg.get("reply_count", 0),
                }
                for msg in response.get("messages", [])
            ]
            return {
                "replies": replies,
                "channel_id": channel_id.strip(),
                "thread_ts": thread_ts.strip(),
            }

        # ----------------------------------------------------------------
        # search_messages
        # ----------------------------------------------------------------
        if op == "search_messages":
            if not query.strip():
                return {"error": "query is required for search_messages."}

            try:
                response = client.search_messages(
                    query=query.strip(),
                    count=bounded_limit,
                )
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            raw_matches = (
                response.get("messages", {}).get("matches", [])
            )
            matches = [
                {
                    "text": m.get("text", ""),
                    "channel": m.get("channel", {}).get("name", ""),
                    "ts": m.get("ts", ""),
                    "permalink": m.get("permalink", ""),
                    "username": m.get("username", ""),
                }
                for m in raw_matches
            ]
            total = response.get("messages", {}).get("total", len(matches))
            return {"matches": matches, "total": total, "query": query.strip()}

        # ----------------------------------------------------------------
        # get_channel_info
        # ----------------------------------------------------------------
        if op == "get_channel_info":
            if not channel_id.strip():
                return {"error": "channel_id is required for get_channel_info."}

            try:
                response = client.conversations_info(channel=channel_id.strip())
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            ch = response.get("channel", {})
            return {
                "channel": {
                    "id": ch.get("id", ""),
                    "name": ch.get("name", ""),
                    "topic": ch.get("topic", {}).get("value", ""),
                    "purpose": ch.get("purpose", {}).get("value", ""),
                    "member_count": ch.get("num_members", 0),
                    "created": ch.get("created", 0),
                    "is_private": ch.get("is_private", False),
                }
            }

        # ----------------------------------------------------------------
        # Unsupported operation
        # ----------------------------------------------------------------
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                "Valid operations: list_channels, get_channel_history, "
                "get_thread_replies, search_messages, get_channel_info."
            )
        }
