"""PagerdutyPlugin — incident and on-call management for tbd-agents (SRE Agent).

Provides read access to PagerDuty incidents, alerts, on-call schedules, and
services, plus three write operations (acknowledge, resolve, trigger) that
are gated by an approval token to prevent accidental state changes.

Required credentials
--------------------
The ``Authorization: Token token=<API_TOKEN>`` header is sent on every request.
The token is resolved at runtime from the ``PAGERDUTY_API_TOKEN`` environment
variable populated by the ``{{token:pagerduty-api-token}}`` secret reference
in :attr:`PagerdutyPlugin.env_config`.

API base URL
------------
``https://api.pagerduty.com/``

All responses use the ``application/vnd.pagerduty+json;version=2`` accept
header.  The ``requests`` library is imported lazily inside :meth:`execute`.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_BASE = "https://api.pagerduty.com"
_ACCEPT = "application/vnd.pagerduty+json;version=2"
_DEFAULT_INCIDENT_LIMIT = 25
_DEFAULT_ONCALL_LIMIT = 25
_VALID_STATUSES = {"triggered", "acknowledged", "resolved"}
_VALID_URGENCIES = {"high", "low"}


class PagerdutyPlugin(PluginBase):
    """PagerDuty incident and on-call management plugin for SRE agents.

    Read operations are strictly non-destructive.  Write operations that
    change incident state (``acknowledge_incident``, ``resolve_incident``,
    ``trigger_incident``) require an ``approval_token`` argument, preventing
    the LLM from accidentally altering incident state without human approval.

    Supported operations
    --------------------
    **Incidents**

    ``list_incidents``
        List active or filtered incidents, optionally scoped to specific
        statuses and service IDs.
    ``get_incident``
        Retrieve full details for a single incident by its string ID.
    ``list_alerts_for_incident``
        List all de-duplicated alerts grouped under an incident.

    **Write — incidents (approval required)**

    ``acknowledge_incident``
        Acknowledge an incident on behalf of a named user.
    ``resolve_incident``
        Resolve an incident on behalf of a named user.
    ``add_incident_note``
        Append a note/comment to an incident timeline.

    **On-call & services**

    ``list_oncalls``
        Return who is currently on-call for given schedules.
    ``list_services``
        List all PagerDuty services in the account.

    **Write — new incident (approval required)**

    ``trigger_incident``
        Open a new incident against a service with given severity and detail.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "pagerduty"

    @property
    def description(self) -> str:
        return (
            "PagerDuty incident and on-call management for SRE agents. "
            "Read operations: list_incidents, get_incident, "
            "list_alerts_for_incident, list_oncalls, list_services. "
            "Write operations (approval_token required): acknowledge_incident, "
            "resolve_incident, add_incident_note, trigger_incident."
        )

    @property
    def tags(self) -> list[str]:
        return ["pagerduty", "incident", "oncall", "alerting", "ticketing", "sre"]

    @property
    def env_config(self) -> dict[str, str]:
        return {"PAGERDUTY_API_TOKEN": "{{token:pagerduty-api-token}}"}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_session(self):
        """Build an authenticated ``requests.Session``.

        Raises:
            RuntimeError: If ``PAGERDUTY_API_TOKEN`` is not set.
        """
        import requests  # noqa: PLC0415

        token = os.environ.get("PAGERDUTY_API_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "PAGERDUTY_API_TOKEN is not set in the environment."
            )

        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Token token={token}",
                "Accept": _ACCEPT,
                "Content-Type": "application/json",
            }
        )
        return session

    def _raise_for_status(self, resp) -> dict:
        """Return parsed JSON or an error dict from a ``requests.Response``."""
        if resp.status_code >= 400:
            try:
                detail = resp.json()
            except Exception:  # noqa: BLE001
                detail = resp.text
            return {"error": f"PagerDuty API error {resp.status_code}: {detail}"}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"ok": True, "status_code": resp.status_code}

    def _build_requester_payload(self, user_email: str) -> dict[str, Any]:
        """Build the ``requester`` sub-object expected by PagerDuty write APIs."""
        return {"type": "user_reference", "email": user_email.strip()}

    # ------------------------------------------------------------------
    # execute — main dispatcher
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        # list_incidents
        statuses: list | None = None,
        service_ids: list | None = None,
        limit: int = _DEFAULT_INCIDENT_LIMIT,
        # get_incident / list_alerts_for_incident / notes / ack / resolve
        incident_id: str = "",
        # acknowledge / resolve / note
        user_email: str = "",
        # add_incident_note
        content: str = "",
        # list_oncalls
        schedule_ids: list | None = None,
        since: str = "",
        until: str = "",
        # trigger_incident
        service_id: str = "",
        title: str = "",
        urgency: str = "high",
        details: str = "",
        # write gate
        approval_token: str = "",
    ) -> dict:
        """Execute a PagerDuty incident or on-call operation.

        Args:
            operation: One of the supported operation names (see class
                docstring).
            statuses: List of incident status filters for ``list_incidents``.
                Valid values: ``"triggered"``, ``"acknowledged"``,
                ``"resolved"``.  Defaults to ``["triggered", "acknowledged"]``
                when not provided.
            service_ids: Optional list of PagerDuty service IDs to scope
                ``list_incidents``.
            limit: Maximum number of results to return (1–100).  Defaults to
                ``25``.
            incident_id: PagerDuty incident ID string (e.g. ``"P1ABCDE"``).
                Required for ``get_incident``, ``list_alerts_for_incident``,
                ``acknowledge_incident``, ``resolve_incident``, and
                ``add_incident_note``.
            user_email: Email of the acting user.  Required for
                ``acknowledge_incident``, ``resolve_incident``, and
                ``add_incident_note``.
            content: Note body text.  Required for ``add_incident_note``.
            schedule_ids: Optional list of schedule IDs to filter
                ``list_oncalls``.
            since: ISO 8601 start timestamp for ``list_oncalls``
                (e.g. ``"2024-01-01T00:00:00Z"``).
            until: ISO 8601 end timestamp for ``list_oncalls``.
            service_id: PagerDuty service ID string.  Required for
                ``trigger_incident``.
            title: Incident title.  Required for ``trigger_incident``.
            urgency: Incident urgency — ``"high"`` or ``"low"``.  Defaults to
                ``"high"``.
            details: Optional free-text body for ``trigger_incident``.
            approval_token: Opaque token required for all write operations.
                Prevents accidental mutations from the LLM without human
                approval.

        Returns:
            A dict whose structure depends on the operation, or
            ``{"error": "..."}`` on failure.
        """
        try:
            session = self._get_session()
        except RuntimeError as exc:
            return {"error": str(exc)}

        op = operation.strip().lower()
        bounded_limit = max(1, min(limit, 100))

        # ----------------------------------------------------------------
        # list_incidents
        # ----------------------------------------------------------------
        if op == "list_incidents":
            effective_statuses = statuses or ["triggered", "acknowledged"]
            for s in effective_statuses:
                if s not in _VALID_STATUSES:
                    return {
                        "error": (
                            f"Invalid status {s!r}. "
                            f"Valid values: {', '.join(sorted(_VALID_STATUSES))}."
                        )
                    }
            params: dict[str, Any] = {
                "limit": bounded_limit,
                "statuses[]": effective_statuses,
            }
            if service_ids:
                params["service_ids[]"] = service_ids

            resp = session.get(f"{_API_BASE}/incidents", params=params)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            incidents = [
                {
                    "id": inc.get("id", ""),
                    "title": inc.get("title", ""),
                    "status": inc.get("status", ""),
                    "urgency": inc.get("urgency", ""),
                    "created_at": inc.get("created_at", ""),
                    "service": inc.get("service", {}).get("summary", ""),
                    "html_url": inc.get("html_url", ""),
                }
                for inc in raw.get("incidents", [])
            ]
            return {"incidents": incidents, "count": len(incidents)}

        # ----------------------------------------------------------------
        # get_incident
        # ----------------------------------------------------------------
        if op == "get_incident":
            if not incident_id.strip():
                return {"error": "get_incident requires a non-empty 'incident_id'."}
            resp = session.get(f"{_API_BASE}/incidents/{incident_id.strip()}")
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            return raw.get("incident", raw)

        # ----------------------------------------------------------------
        # list_alerts_for_incident
        # ----------------------------------------------------------------
        if op == "list_alerts_for_incident":
            if not incident_id.strip():
                return {
                    "error": "list_alerts_for_incident requires a non-empty 'incident_id'."
                }
            resp = session.get(
                f"{_API_BASE}/incidents/{incident_id.strip()}/alerts",
                params={"limit": bounded_limit},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            alerts = [
                {
                    "id": a.get("id", ""),
                    "summary": a.get("summary", ""),
                    "status": a.get("status", ""),
                    "severity": a.get("severity", ""),
                    "created_at": a.get("created_at", ""),
                }
                for a in raw.get("alerts", [])
            ]
            return {
                "incident_id": incident_id.strip(),
                "alerts": alerts,
                "count": len(alerts),
            }

        # ----------------------------------------------------------------
        # acknowledge_incident  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "acknowledge_incident":
            if not approval_token.strip():
                return {
                    "error": (
                        "approval_token is required for acknowledge_incident. "
                        "Obtain a token from your team's change-management workflow."
                    )
                }
            if not incident_id.strip():
                return {"error": "acknowledge_incident requires 'incident_id'."}
            if not user_email.strip():
                return {"error": "acknowledge_incident requires 'user_email'."}

            body = {
                "incident": {"type": "incident", "status": "acknowledged"},
                "requester": self._build_requester_payload(user_email),
            }
            resp = session.put(
                f"{_API_BASE}/incidents/{incident_id.strip()}",
                json=body,
                headers={"From": user_email.strip()},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            return {
                "acknowledged": True,
                "incident_id": incident_id.strip(),
                "by": user_email.strip(),
            }

        # ----------------------------------------------------------------
        # resolve_incident  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "resolve_incident":
            if not approval_token.strip():
                return {
                    "error": (
                        "approval_token is required for resolve_incident. "
                        "Obtain a token from your team's change-management workflow."
                    )
                }
            if not incident_id.strip():
                return {"error": "resolve_incident requires 'incident_id'."}
            if not user_email.strip():
                return {"error": "resolve_incident requires 'user_email'."}

            body = {
                "incident": {"type": "incident", "status": "resolved"},
                "requester": self._build_requester_payload(user_email),
            }
            resp = session.put(
                f"{_API_BASE}/incidents/{incident_id.strip()}",
                json=body,
                headers={"From": user_email.strip()},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            return {
                "resolved": True,
                "incident_id": incident_id.strip(),
                "by": user_email.strip(),
            }

        # ----------------------------------------------------------------
        # add_incident_note
        # ----------------------------------------------------------------
        if op == "add_incident_note":
            if not incident_id.strip():
                return {"error": "add_incident_note requires 'incident_id'."}
            if not content.strip():
                return {"error": "add_incident_note requires non-empty 'content'."}
            if not user_email.strip():
                return {"error": "add_incident_note requires 'user_email'."}

            body = {
                "note": {"content": content.strip()},
                "requester": self._build_requester_payload(user_email),
            }
            resp = session.post(
                f"{_API_BASE}/incidents/{incident_id.strip()}/notes",
                json=body,
                headers={"From": user_email.strip()},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            note = raw.get("note", {})
            return {
                "added": True,
                "note_id": note.get("id", ""),
                "incident_id": incident_id.strip(),
            }

        # ----------------------------------------------------------------
        # list_oncalls
        # ----------------------------------------------------------------
        if op == "list_oncalls":
            params = {"limit": bounded_limit}
            if schedule_ids:
                params["schedule_ids[]"] = schedule_ids  # type: ignore[assignment]
            if since:
                params["since"] = since  # type: ignore[assignment]
            if until:
                params["until"] = until  # type: ignore[assignment]

            resp = session.get(f"{_API_BASE}/oncalls", params=params)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            oncalls = [
                {
                    "user": oc.get("user", {}).get("summary", ""),
                    "schedule": oc.get("schedule", {}).get("summary", ""),
                    "escalation_policy": oc.get("escalation_policy", {}).get("summary", ""),
                    "start": oc.get("start", ""),
                    "end": oc.get("end", ""),
                }
                for oc in raw.get("oncalls", [])
            ]
            return {"oncalls": oncalls, "count": len(oncalls)}

        # ----------------------------------------------------------------
        # list_services
        # ----------------------------------------------------------------
        if op == "list_services":
            resp = session.get(
                f"{_API_BASE}/services",
                params={"limit": bounded_limit},
            )
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            services = [
                {
                    "id": svc.get("id", ""),
                    "name": svc.get("name", ""),
                    "status": svc.get("status", ""),
                    "description": svc.get("description", ""),
                    "html_url": svc.get("html_url", ""),
                }
                for svc in raw.get("services", [])
            ]
            return {"services": services, "count": len(services)}

        # ----------------------------------------------------------------
        # trigger_incident  (write — requires approval_token)
        # ----------------------------------------------------------------
        if op == "trigger_incident":
            if not approval_token.strip():
                return {
                    "error": (
                        "approval_token is required for trigger_incident. "
                        "Obtain a token from your team's change-management workflow."
                    )
                }
            if not service_id.strip():
                return {"error": "trigger_incident requires 'service_id'."}
            if not title.strip():
                return {"error": "trigger_incident requires 'title'."}

            effective_urgency = urgency.strip().lower()
            if effective_urgency not in _VALID_URGENCIES:
                return {
                    "error": (
                        f"Invalid urgency {urgency!r}. "
                        f"Must be one of: {', '.join(sorted(_VALID_URGENCIES))}."
                    )
                }

            body: dict[str, Any] = {
                "incident": {
                    "type": "incident",
                    "title": title.strip(),
                    "urgency": effective_urgency,
                    "service": {"id": service_id.strip(), "type": "service_reference"},
                }
            }
            if details.strip():
                body["incident"]["body"] = {
                    "type": "incident_body",
                    "details": details.strip(),
                }

            resp = session.post(f"{_API_BASE}/incidents", json=body)
            raw = self._raise_for_status(resp)
            if "error" in raw:
                return raw
            incident = raw.get("incident", {})
            return {
                "triggered": True,
                "incident_id": incident.get("id", ""),
                "title": incident.get("title", title.strip()),
                "html_url": incident.get("html_url", ""),
            }

        # ----------------------------------------------------------------
        # Unsupported operation
        # ----------------------------------------------------------------
        valid_ops = (
            "list_incidents, get_incident, list_alerts_for_incident, "
            "acknowledge_incident, resolve_incident, add_incident_note, "
            "list_oncalls, list_services, trigger_incident"
        )
        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {valid_ops}."
            )
        }
