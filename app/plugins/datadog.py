"""DatadogPlugin — observability integration for tbd-agents (SRE Agent).

Provides read-heavy access to Datadog metrics, logs, monitors, events, SLOs,
and host tags, plus two narrow write operations (mute a monitor, create an
event) that are gated by an approval token.

Required credentials
--------------------
``DD-API-KEY`` and ``DD-APPLICATION-KEY`` headers are sent on every request.
Both are resolved at runtime from environment variables populated by the
``{{token:...}}`` secret references in :attr:`DatadogPlugin.env_config`.

API versions used
-----------------
* ``/api/v1/`` — metrics timeseries, monitors, events, hosts, SLOs
* ``/api/v2/`` — logs query (``/api/v2/logs/events/search``)

All HTTP calls use the ``requests`` library, imported lazily inside
:meth:`execute` so the plugin can be imported without ``requests`` installed.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SITE = "datadoghq.com"
_V1 = "https://api.{site}/api/v1"
_V2 = "https://api.{site}/api/v2"
_DEFAULT_LOG_LIMIT = 50
_DEFAULT_EVENT_LIMIT = 50
_DEFAULT_MONITOR_LIMIT = 100
_VALID_ALERT_TYPES = {"error", "warning", "info", "success", "user_update",
                      "recommendation", "snapshot"}


class DatadogPlugin(PluginBase):
    """Datadog observability plugin for SRE agents.

    Exposes read operations for metrics, logs, monitors, events, SLOs, and
    host tags, plus two write operations (mute a monitor and create an event)
    that require an ``approval_token`` to prevent accidental mutations.

    Supported operations
    --------------------
    **Metrics**

    ``query_metrics``
        Query Datadog timeseries metrics using a DQL expression.  Returns
        the series data between two Unix timestamps.

    **Logs**

    ``query_logs``
        Search Datadog log events via the Logs Search v2 API.

    **Monitors**

    ``list_monitors``
        List all monitors in the account (paginated, returns up to
        ``_DEFAULT_MONITOR_LIMIT`` by default).
    ``get_monitor``
        Retrieve full details for a single monitor by ID.

    **Events**

    ``list_events``
        List recent events from the Datadog event stream.
    ``query_events``
        Search events by text query within a time range.

    **SLOs**

    ``query_slo``
        Retrieve SLO history (error budget, SLI) for a given time range.

    **Hosts**

    ``get_host_tags``
        Get all tags applied to a specific host.

    **Write (approval required)**

    ``mute_monitor``
        Mute a monitor until a given timestamp.  Requires ``approval_token``.
    ``create_event``
        Post a custom event to the Datadog event stream.  Requires
        ``approval_token``.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "datadog"

    @property
    def description(self) -> str:
        return (
            "Datadog observability integration for SRE agents. "
            "Read operations: query_metrics (timeseries DQL), query_logs "
            "(v2 log search), list_monitors, get_monitor, list_events, "
            "query_events, query_slo (SLO history), get_host_tags. "
            "Write operations (approval_token required): mute_monitor, "
            "create_event."
        )

    @property
    def tags(self) -> list[str]:
        return ["datadog", "observability", "metrics", "logs", "monitors", "sre"]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "DATADOG_API_KEY": "{{token:datadog-api-key}}",
            "DATADOG_APP_KEY": "{{token:datadog-app-key}}",
            "DATADOG_SITE": _DEFAULT_SITE,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_session(self):
        """Build an authenticated ``requests.Session``.

        Raises:
            RuntimeError: If ``DATADOG_API_KEY`` or ``DATADOG_APP_KEY`` are
                not set in the environment.
        """
        import requests  # noqa: PLC0415

        api_key = os.environ.get("DATADOG_API_KEY", "").strip()
        app_key = os.environ.get("DATADOG_APP_KEY", "").strip()

        if not api_key:
            raise RuntimeError(
                "DATADOG_API_KEY is not set in the environment."
            )
        if not app_key:
            raise RuntimeError(
                "DATADOG_APP_KEY is not set in the environment."
            )

        session = requests.Session()
        session.headers.update(
            {
                "DD-API-KEY": api_key,
                "DD-APPLICATION-KEY": app_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        return session

    def _base_v1(self) -> str:
        site = os.environ.get("DATADOG_SITE", _DEFAULT_SITE).strip() or _DEFAULT_SITE
        return _V1.format(site=site)

    def _base_v2(self) -> str:
        site = os.environ.get("DATADOG_SITE", _DEFAULT_SITE).strip() or _DEFAULT_SITE
        return _V2.format(site=site)

    def _raise_for_status(self, resp) -> dict:
        """Check HTTP status and return JSON body or error dict."""
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:  # noqa: BLE001
                detail = resp.text
            return {"error": f"Datadog API error {resp.status_code}: {detail}"}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"ok": True, "status_code": resp.status_code}

    # ------------------------------------------------------------------
    # execute — main dispatcher
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        # query_metrics / query_logs / query_events / query_slo
        query: str = "",
        from_ts: int = 0,
        to_ts: int = 0,
        # query_logs extras
        limit: int = _DEFAULT_LOG_LIMIT,
        sort: str = "timestamp",
        # get_monitor / mute_monitor
        monitor_id: int = 0,
        # query_slo
        slo_id: str = "",
        # get_host_tags
        host: str = "",
        # mute_monitor
        end_ts: int = 0,
        # create_event
        title: str = "",
        text: str = "",
        tags: list | None = None,
        alert_type: str = "info",
        # write-gate
        approval_token: str = "",
    ) -> dict:
        """Execute a Datadog observability operation.

        Args:
            operation: One of the supported operation names (see class
                docstring).
            query: Metrics DQL expression (``query_metrics``, ``query_events``)
                or Logs query string (``query_logs``).
            from_ts: Start of the query window as a Unix epoch integer
                (seconds).  Required for ``query_metrics``, ``query_logs``,
                ``query_events``, and ``query_slo``.
            to_ts: End of the query window as a Unix epoch integer (seconds).
                Required for the same operations as ``from_ts``.
            limit: Maximum number of log or event results to return (capped
                at 1000).  Defaults to ``50``.
            sort: Log sort order — ``"timestamp"`` (oldest first) or
                ``"-timestamp"`` (newest first).  Defaults to ``"timestamp"``.
            monitor_id: Numeric Datadog monitor ID.  Required for
                ``get_monitor`` and ``mute_monitor``.
            slo_id: Datadog SLO public ID (string).  Required for
                ``query_slo``.
            host: Hostname string.  Required for ``get_host_tags``.
            end_ts: Unix epoch (seconds) indicating when the mute should
                expire.  Required for ``mute_monitor``.
            title: Event title.  Required for ``create_event``.
            text: Event body text.  Required for ``create_event``.
            tags: Optional list of tag strings (e.g. ``["env:prod",
                "team:sre"]``) attached to ``create_event``.
            alert_type: Datadog alert type for ``create_event``.  Must be one
                of ``error``, ``warning``, ``info``, ``success``,
                ``user_update``, ``recommendation``, ``snapshot``.  Defaults
                to ``"info"``.
            approval_token: Opaque token required for write operations
                (``mute_monitor``, ``create_event``).  Prevents accidental
                mutations when the agent runs without explicit human approval.

        Returns:
            A dict whose structure depends on the operation, or
            ``{"error": "..."}`` on failure.
        """
        try:
            session = self._get_session()
        except RuntimeError as exc:
            return {"error": str(exc)}

        op = operation.strip().lower()

        # ----------------------------------------------------------------
        # query_metrics
        # ----------------------------------------------------------------
        if op == "query_metrics":
            if not query.strip():
                return {"error": "query_metrics requires a non-empty 'query' expression."}
            if not from_ts or not to_ts:
                return {"error": "query_metrics requires 'from_ts' and 'to_ts' (Unix seconds)."}

            url = f"{self._base_v1()}/query"
            resp = session.get(
                url,
                params={"query": query.strip(), "from": from_ts, "to": to_ts},
            )
            return self._raise_for_status(resp)

        # ----------------------------------------------------------------
        # query_logs
        # ----------------------------------------------------------------
        if op == "query_logs":
            if not query.strip():
                return {"error": "query_logs requires a non-empty 'query' string."}
            if not from_ts or not to_ts:
                return {"error": "query_logs requires 'from_ts' and 'to_ts' (Unix seconds)."}

            bounded_limit = max(1, min(limit, 1000))
            url = f"{self._base_v2()}/logs/events/search"
            body: dict[str, Any] = {
                "filter": {
                    "query": query.strip(),
                    "from": from_ts,
                    "to": to_ts,
                },
                "sort": sort,
                "page": {"limit": bounded_limit},
            }
            resp = session.post(url, json=body)
            return self._raise_for_status(resp)

        # ----------------------------------------------------------------
        # list_monitors
        # ----------------------------------------------------------------
        if op == "list_monitors":
            url = f"{self._base_v1()}/monitor"
            resp = session.get(
                url,
                params={"page_size": _DEFAULT_MONITOR_LIMIT},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            monitors = [
                {
                    "id": m.get("id"),
                    "name": m.get("name", ""),
                    "type": m.get("type", ""),
                    "status": m.get("overall_state", ""),
                    "tags": m.get("tags", []),
                    "query": m.get("query", ""),
                }
                for m in (raw if isinstance(raw, list) else [])
            ]
            return {"monitors": monitors, "count": len(monitors)}

        # ----------------------------------------------------------------
        # get_monitor
        # ----------------------------------------------------------------
        if op == "get_monitor":
            if not monitor_id:
                return {"error": "get_monitor requires a non-zero 'monitor_id'."}
            url = f"{self._base_v1()}/monitor/{monitor_id}"
            resp = session.get(url)
            return self._raise_for_status(resp)

        # ----------------------------------------------------------------
        # list_events
        # ----------------------------------------------------------------
        if op == "list_events":
            if not from_ts or not to_ts:
                return {"error": "list_events requires 'from_ts' and 'to_ts' (Unix seconds)."}
            bounded_limit = max(1, min(limit, 1000))
            url = f"{self._base_v1()}/events"
            resp = session.get(
                url,
                params={
                    "start": from_ts,
                    "end": to_ts,
                    "count": bounded_limit,
                },
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            events = raw.get("events", [])
            return {"events": events, "count": len(events)}

        # ----------------------------------------------------------------
        # query_events
        # ----------------------------------------------------------------
        if op == "query_events":
            if not from_ts or not to_ts:
                return {"error": "query_events requires 'from_ts' and 'to_ts' (Unix seconds)."}
            bounded_limit = max(1, min(limit, 1000))
            url = f"{self._base_v1()}/events"
            params: dict[str, Any] = {
                "start": from_ts,
                "end": to_ts,
                "count": bounded_limit,
            }
            if query.strip():
                params["tags"] = query.strip()
            resp = session.get(url, params=params)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            events = raw.get("events", [])
            return {
                "events": events,
                "count": len(events),
                "query": query.strip(),
            }

        # ----------------------------------------------------------------
        # query_slo
        # ----------------------------------------------------------------
        if op == "query_slo":
            if not slo_id.strip():
                return {"error": "query_slo requires a non-empty 'slo_id'."}
            if not from_ts or not to_ts:
                return {"error": "query_slo requires 'from_ts' and 'to_ts' (Unix seconds)."}
            url = f"{self._base_v1()}/slo/{slo_id.strip()}/history"
            resp = session.get(
                url,
                params={"from_ts": from_ts, "to_ts": to_ts},
            )
            return self._raise_for_status(resp)

        # ----------------------------------------------------------------
        # get_host_tags
        # ----------------------------------------------------------------
        if op == "get_host_tags":
            if not host.strip():
                return {"error": "get_host_tags requires a non-empty 'host' name."}
            url = f"{self._base_v1()}/tags/hosts/{host.strip()}"
            resp = session.get(url)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            return {"host": host.strip(), "tags": raw.get("tags", [])}

        # ----------------------------------------------------------------
        # mute_monitor  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "mute_monitor":
            if not approval_token.strip():
                return {
                    "error": (
                        "approval_token is required for mute_monitor. "
                        "Obtain a token from your team's change-management workflow."
                    )
                }
            if not monitor_id:
                return {"error": "mute_monitor requires a non-zero 'monitor_id'."}
            if not end_ts:
                return {"error": "mute_monitor requires 'end_ts' (Unix epoch expiry seconds)."}

            url = f"{self._base_v1()}/monitor/{monitor_id}/mute"
            body = {"end": end_ts}
            resp = session.post(url, json=body)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            return {
                "muted": True,
                "monitor_id": monitor_id,
                "end_ts": end_ts,
            }

        # ----------------------------------------------------------------
        # create_event  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "create_event":
            if not approval_token.strip():
                return {
                    "error": (
                        "approval_token is required for create_event. "
                        "Obtain a token from your team's change-management workflow."
                    )
                }
            if not title.strip():
                return {"error": "create_event requires a non-empty 'title'."}
            if not text.strip():
                return {"error": "create_event requires a non-empty 'text'."}

            effective_alert_type = alert_type.strip().lower()
            if effective_alert_type not in _VALID_ALERT_TYPES:
                return {
                    "error": (
                        f"Invalid alert_type {alert_type!r}. "
                        f"Must be one of: {', '.join(sorted(_VALID_ALERT_TYPES))}."
                    )
                }

            url = f"{self._base_v1()}/events"
            body = {
                "title": title.strip(),
                "text": text.strip(),
                "alert_type": effective_alert_type,
                "tags": tags or [],
            }
            resp = session.post(url, json=body)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            event = raw.get("event", {})
            return {
                "created": True,
                "event_id": event.get("id"),
                "url": event.get("url", ""),
            }

        # ----------------------------------------------------------------
        # Unsupported operation
        # ----------------------------------------------------------------
        valid_ops = (
            "query_metrics, query_logs, list_monitors, get_monitor, "
            "list_events, query_events, query_slo, get_host_tags, "
            "mute_monitor, create_event"
        )
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {valid_ops}."
            )
        }
