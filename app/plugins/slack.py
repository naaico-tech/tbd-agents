"""SlackPlugin — read and write Slack integration for tbd-agents.

Provides channel browsing, message history, thread access, keyword search,
and outbound messaging (send to channels, reply in threads, add reactions).

Required Slack bot token scopes
---------------------------------
Read operations:
  - channels:read      (list_channels, get_channel_info)
  - channels:history   (get_channel_history, get_thread_replies)
  - search:read        (search_messages — requires user token, not bot token)

Write operations:
  - chat:write         (send_message, reply_in_thread)
  - reactions:write    (add_reaction)

The bot token is resolved at runtime via the ``SLACK_BOT_TOKEN`` environment
variable, which is populated from the ``{{token:slack-bot-token}}`` secret.
"""

from __future__ import annotations

import os

from app.core.plugin_base import PluginBase

#: Maximum number of results that can be requested in a single call.
_MAX_LIMIT = 200


class SlackPlugin(PluginBase):
    """Slack plugin with read and messaging (write) capabilities.

    Read operations are strictly non-destructive.  Write operations are limited
    to sending and reacting to messages — no channels or users are modified.
    All API calls are delegated to the official ``slack-sdk`` ``WebClient``,
    imported lazily inside :meth:`execute`.

    Supported operations
    --------------------
    **Read**

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

    **Write**

    ``send_message``
        Post a message to a channel (plain text or Block Kit blocks).
    ``reply_in_thread``
        Post a threaded reply to an existing message.
    ``add_reaction``
        Add an emoji reaction to a specific message.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "slack"

    @property
    def description(self) -> str:
        return (
            "Slack integration: list channels, fetch message history, read thread "
            "replies, search by keyword, get channel details, send messages to "
            "channels, post threaded replies, and add emoji reactions."
        )

    @property
    def tags(self) -> list[str]:
        return ["slack", "messaging", "communication", "notifications"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"SLACK_BOT_TOKEN": "{{token:slack-bot-token}}"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):  # type: ignore[return]
        """Build and return a configured ``WebClient``.

        Raises:
            RuntimeError: If ``SLACK_BOT_TOKEN`` is not set in the environment.
        """
        from slack_sdk import WebClient  # noqa: PLC0415

        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise RuntimeError("SLACK_BOT_TOKEN is not set in the environment.")
        return WebClient(token=token)

    def _resolve_channel_id(self, client, channel_name: str, limit: int) -> str | None:
        """Resolve a channel name to its Slack channel ID."""
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
        text: str = "",
        blocks: list | None = None,
        emoji: str = "",
        limit: int = 50,
        cursor: str = "",
    ) -> dict:
        """Perform a Slack read or messaging operation.

        Args:
            operation: One of the supported operation names (see class docstring).
            channel_id: Slack channel ID (e.g. ``C01234ABCDE``).  Required for
                ``get_channel_history`` (unless ``channel_name`` is given),
                ``get_thread_replies``, ``get_channel_info``, ``send_message``,
                ``reply_in_thread``, and ``add_reaction``.
            channel_name: Human-readable channel name (e.g. ``general`` or
                ``#general``).  Used as a fallback for ``get_channel_history``
                and ``send_message`` when ``channel_id`` is not supplied.
            thread_ts: Timestamp of the parent message (e.g.
                ``1715000000.000100``).  Required for ``get_thread_replies``,
                ``reply_in_thread``, and ``add_reaction``.
            query: Keyword query string.  Required for ``search_messages``.
            text: Message text (plain text or mrkdwn).  Required for
                ``send_message`` and ``reply_in_thread`` unless ``blocks``
                is provided.
            blocks: Optional list of `Block Kit
                <https://api.slack.com/block-kit>`_ block dicts for rich
                message formatting in ``send_message`` and ``reply_in_thread``.
                When provided, ``text`` is used as the plain-text fallback.
            emoji: Emoji name **without** colons (e.g. ``thumbsup``).  Required
                for ``add_reaction``.
            limit: Maximum number of items to return (clamped to 1–200).
                Defaults to ``50``.
            cursor: Pagination cursor returned by a previous call.  Used by
                ``list_channels`` and ``get_channel_history``.

        Returns:
            A dict whose structure depends on the operation:

            Read operations:

            * ``list_channels``      → ``{"channels": [...], "next_cursor": ""}``
            * ``get_channel_history``→ ``{"messages": [...], "channel_id": ""}``
            * ``get_thread_replies`` → ``{"replies": [...], "channel_id": "", "thread_ts": ""}``
            * ``search_messages``    → ``{"matches": [...], "total": int, "query": ""}``
            * ``get_channel_info``   → ``{"channel": {...}}``

            Write operations:

            * ``send_message``       → ``{"ok": true, "ts": "...", "channel": "..."}``
            * ``reply_in_thread``    → ``{"ok": true, "ts": "...", "channel": "...", "thread_ts": "..."}``
            * ``add_reaction``       → ``{"ok": true}``

            On error → ``{"error": "..."}``
        """
        from slack_sdk.errors import SlackApiError  # noqa: PLC0415

        bounded_limit = max(1, min(limit, _MAX_LIMIT))
        op = operation.strip().lower()

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
            if not resolved_id and channel_name:
                resolved_id = (
                    self._resolve_channel_id(client, channel_name, bounded_limit) or ""
                )
            if not resolved_id:
                return {
                    "error": "channel_id or channel_name is required for get_channel_history."
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

            raw_matches = response.get("messages", {}).get("matches", [])
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
        # send_message
        # ----------------------------------------------------------------
        if op == "send_message":
            resolved_id = channel_id.strip()
            if not resolved_id and channel_name:
                resolved_id = (
                    self._resolve_channel_id(client, channel_name, _MAX_LIMIT) or ""
                )
            if not resolved_id:
                return {
                    "error": "channel_id or channel_name is required for send_message."
                }
            if not text.strip() and not blocks:
                return {"error": "text or blocks is required for send_message."}

            kwargs: dict = {"channel": resolved_id, "text": text}
            if blocks:
                kwargs["blocks"] = blocks

            try:
                response = client.chat_postMessage(**kwargs)
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            return {
                "ok": True,
                "ts": response.get("ts", ""),
                "channel": response.get("channel", resolved_id),
            }

        # ----------------------------------------------------------------
        # reply_in_thread
        # ----------------------------------------------------------------
        if op == "reply_in_thread":
            resolved_id = channel_id.strip()
            if not resolved_id and channel_name:
                resolved_id = (
                    self._resolve_channel_id(client, channel_name, _MAX_LIMIT) or ""
                )
            if not resolved_id:
                return {
                    "error": "channel_id or channel_name is required for reply_in_thread."
                }
            if not thread_ts.strip():
                return {"error": "thread_ts is required for reply_in_thread."}
            if not text.strip() and not blocks:
                return {"error": "text or blocks is required for reply_in_thread."}

            kwargs = {
                "channel": resolved_id,
                "thread_ts": thread_ts.strip(),
                "text": text,
            }
            if blocks:
                kwargs["blocks"] = blocks

            try:
                response = client.chat_postMessage(**kwargs)
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            return {
                "ok": True,
                "ts": response.get("ts", ""),
                "channel": response.get("channel", resolved_id),
                "thread_ts": thread_ts.strip(),
            }

        # ----------------------------------------------------------------
        # add_reaction
        # ----------------------------------------------------------------
        if op == "add_reaction":
            if not channel_id.strip():
                return {"error": "channel_id is required for add_reaction."}
            if not thread_ts.strip():
                return {"error": "thread_ts (message timestamp) is required for add_reaction."}
            if not emoji.strip():
                return {"error": "emoji is required for add_reaction (e.g. 'thumbsup')."}

            try:
                client.reactions_add(
                    channel=channel_id.strip(),
                    timestamp=thread_ts.strip(),
                    name=emoji.strip().strip(":"),
                )
            except SlackApiError as exc:
                return {"error": exc.response["error"]}

            return {"ok": True}

        # ----------------------------------------------------------------
        # Unsupported operation
        # ----------------------------------------------------------------
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                "Valid operations: list_channels, get_channel_history, "
                "get_thread_replies, search_messages, get_channel_info, "
                "send_message, reply_in_thread, add_reaction."
            )
        }
