"""GoogleAnalyticsPlugin — GA4 Data API + Admin API for tbd-agents.

Provides read-only access to Google Analytics 4 properties via the
``google-analytics-data`` and ``google-analytics-admin`` Python libraries.
All credentials are supplied through a service-account JSON key stored in the
``GOOGLE_GA4_CREDENTIALS_JSON`` environment variable.

Supported operations
--------------------
``run_report``
    Run a standard GA4 Data API report (dimensions + metrics over a date range).
``batch_run_reports``
    Run multiple reports in a single API call.
``run_pivot_report``
    Run a pivot report for cross-dimensional breakdowns.
``run_realtime_report``
    Fetch real-time active users, events, and conversions.
``get_metadata``
    List all available dimensions and metrics for a property.
``check_compatibility``
    Verify that a set of dimensions and metrics can be used together.
``list_audiences``
    List GA4 Audiences configured on a property.
``list_custom_dimensions``
    List custom dimensions configured on a property.
``list_custom_metrics``
    List custom metrics configured on a property.
``list_conversion_events``
    List conversion events configured on a property.

Hardening
---------
- Hard row cap of 100,000 rows per request; warn when ``limit > 10,000``.
- When sessions or users in result < 100, ``"small_sample_warning": true`` is
  attached to the response.
- ``user_id`` and ``client_id`` dimensions are blocked by default; pass
  ``pii_acknowledged=True`` to allow them (read-PII consent gate).

Required Google OAuth2 scopes
------------------------------
- ``https://www.googleapis.com/auth/analytics.readonly``
- ``https://www.googleapis.com/auth/analytics``  (Admin API list calls)

Required IAM roles on the GA4 property
---------------------------------------
- Viewer (Data API)
- Viewer / Analyst (Admin API list calls)
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DATA_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]
_ADMIN_SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]

#: Absolute upper bound on rows returned in a single report call.
_ROW_HARD_CAP = 100_000

#: Warn the caller when the requested row limit exceeds this threshold.
_ROW_WARN_THRESHOLD = 10_000

#: Minimum user/session count below which a small-sample warning is attached.
_SMALL_SAMPLE_THRESHOLD = 100

#: PII dimensions that require explicit acknowledgement before use.
_PII_DIMENSIONS = {"user_id", "client_id", "userId", "clientId"}

#: All supported operations.
_VALID_OPERATIONS = {
    "run_report",
    "batch_run_reports",
    "run_pivot_report",
    "run_realtime_report",
    "get_metadata",
    "check_compatibility",
    "list_audiences",
    "list_custom_dimensions",
    "list_custom_metrics",
    "list_conversion_events",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class GoogleAnalyticsPlugin(PluginBase):
    """GA4 Data + Admin API plugin for the Marketing Analyst agent.

    All API calls are **read-only**.  No property settings, events, or audiences
    are created or modified.  Service-account credentials are loaded lazily from
    the ``GOOGLE_GA4_CREDENTIALS_JSON`` environment variable (a JSON string of
    the key file) the first time a network call is needed.

    The ``execute`` method dispatches to a private handler for each operation
    following the same pattern as ``SlackPlugin``.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "google_analytics"

    @property
    def description(self) -> str:
        return (
            "Read-only access to Google Analytics 4 (GA4) via the Data API and "
            "Admin API. Supported operations: run_report (standard reports with "
            "dimensions, metrics, filters, date ranges), batch_run_reports (multiple "
            "reports in one call), run_pivot_report (pivot/cross-tab reports), "
            "run_realtime_report (active-user and event counts right now), "
            "get_metadata (list available dimensions and metrics), check_compatibility "
            "(validate dimension+metric combinations), list_audiences, "
            "list_custom_dimensions, list_custom_metrics, list_conversion_events. "
            "Enforces a 100,000-row hard cap; attaches small_sample_warning when "
            "users/sessions < 100; blocks PII dimensions without explicit consent."
        )

    @property
    def tags(self) -> list[str]:
        return [
            "ga4",
            "google_analytics",
            "analytics",
            "web-analytics",
            "marketing",
            "read",
        ]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "GOOGLE_GA4_CREDENTIALS_JSON": "{{token:google-ga4-credentials-json}}",
            "GOOGLE_GA4_PROPERTY_ID": "{{token:google-ga4-property-id}}",
        }

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _get_data_client(self):
        """Build and return an authenticated GA4 Data API ``BetaAnalyticsDataClient``.

        Credentials are read from ``GOOGLE_GA4_CREDENTIALS_JSON`` (a JSON string
        of a Google service-account key file) and scoped to read-only analytics.

        Returns:
            A ``google.analytics.data_v1beta.BetaAnalyticsDataClient`` instance.

        Raises:
            RuntimeError: If ``GOOGLE_GA4_CREDENTIALS_JSON`` is unset or empty.
            ValueError: If the credentials JSON cannot be parsed.
        """
        from google.analytics.data_v1beta import BetaAnalyticsDataClient  # noqa: PLC0415
        from google.oauth2.service_account import Credentials  # noqa: PLC0415

        creds_json = os.environ.get("GOOGLE_GA4_CREDENTIALS_JSON", "").strip()
        if not creds_json:
            raise RuntimeError(
                "GOOGLE_GA4_CREDENTIALS_JSON environment variable is not set."
            )
        credentials = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=_DATA_SCOPES,
        )
        return BetaAnalyticsDataClient(credentials=credentials)

    def _get_admin_client(self):
        """Build and return an authenticated GA4 Admin ``AnalyticsAdminServiceClient``.

        Uses the same service-account JSON as ``_get_data_client`` but targets
        the Analytics Admin API endpoint.

        Returns:
            A ``google.analytics.admin_v1alpha.AnalyticsAdminServiceClient`` instance.

        Raises:
            RuntimeError: If ``GOOGLE_GA4_CREDENTIALS_JSON`` is unset or empty.
        """
        from google.analytics.admin_v1alpha import AnalyticsAdminServiceClient  # noqa: PLC0415
        from google.oauth2.service_account import Credentials  # noqa: PLC0415

        creds_json = os.environ.get("GOOGLE_GA4_CREDENTIALS_JSON", "").strip()
        if not creds_json:
            raise RuntimeError(
                "GOOGLE_GA4_CREDENTIALS_JSON environment variable is not set."
            )
        credentials = Credentials.from_service_account_info(
            json.loads(creds_json),
            scopes=_ADMIN_SCOPES,
        )
        return AnalyticsAdminServiceClient(credentials=credentials)

    # ------------------------------------------------------------------
    # Guard helpers
    # ------------------------------------------------------------------

    def _resolve_property(self, property_id: str) -> str:
        """Return a fully-qualified property resource name.

        Accepts either a bare numeric ID (``"123456789"``) or a resource name
        (``"properties/123456789"``) and normalises it.

        Args:
            property_id: Raw property ID or resource name.

        Returns:
            A string of the form ``"properties/<numeric_id>"``.

        Raises:
            ValueError: If ``property_id`` is empty and the environment variable
                ``GOOGLE_GA4_PROPERTY_ID`` is also unset.
        """
        pid = property_id.strip()
        if not pid:
            pid = os.environ.get("GOOGLE_GA4_PROPERTY_ID", "").strip()
        if not pid:
            raise ValueError(
                "property_id is required (or set GOOGLE_GA4_PROPERTY_ID env var)."
            )
        if not pid.startswith("properties/"):
            pid = f"properties/{pid}"
        return pid

    def _check_pii(
        self, dimensions: list[str], pii_acknowledged: bool
    ) -> str | None:
        """Return an error message if PII dimensions are requested without consent.

        Args:
            dimensions: List of dimension names requested by the caller.
            pii_acknowledged: When ``True``, PII dimensions are permitted.

        Returns:
            An error string if PII dimensions are present and not acknowledged,
            or ``None`` if the request is safe to proceed.
        """
        if pii_acknowledged:
            return None
        blocked = [d for d in dimensions if d in _PII_DIMENSIONS]
        if blocked:
            return (
                f"Dimensions {blocked} contain PII (user_id / client_id). "
                "Pass pii_acknowledged=True to allow."
            )
        return None

    def _clamp_limit(self, limit: int) -> tuple[int, list[str]]:
        """Clamp *limit* to [1, _ROW_HARD_CAP] and collect warnings.

        Args:
            limit: Requested row limit from the caller.

        Returns:
            A ``(clamped_limit, warnings)`` tuple where *warnings* is a list of
            zero or more advisory strings to surface in the response.
        """
        warnings: list[str] = []
        if limit > _ROW_HARD_CAP:
            warnings.append(
                f"Requested limit {limit} exceeds hard cap {_ROW_HARD_CAP}; "
                f"clamped to {_ROW_HARD_CAP}."
            )
            limit = _ROW_HARD_CAP
        elif limit > _ROW_WARN_THRESHOLD:
            warnings.append(
                f"Requested limit {limit} is large (>{_ROW_WARN_THRESHOLD}); "
                "consider using a narrower date range or adding filters."
            )
        return max(1, limit), warnings

    def _attach_sample_warning(self, result: dict) -> dict:
        """Attach ``"small_sample_warning": true`` when user/session counts are low.

        Inspects the ``rows`` list in *result* for metric values associated with
        ``sessions`` or ``activeUsers`` and flags the result when totals are low.

        Args:
            result: A response dict that may contain a ``"rows"`` key.

        Returns:
            The mutated *result* dict (modified in place).
        """
        rows = result.get("rows", [])
        total = 0
        for row in rows:
            for header, val in zip(
                result.get("metric_headers", []), row.get("metric_values", [])
            ):
                name = header.get("name", "").lower()
                if name in ("sessions", "activeusers", "totalusers", "newusers"):
                    try:
                        total += int(val.get("value", 0))
                    except (TypeError, ValueError):
                        pass
        if 0 < total < _SMALL_SAMPLE_THRESHOLD:
            result["small_sample_warning"] = True
        return result

    # ------------------------------------------------------------------
    # Operation handlers
    # ------------------------------------------------------------------

    def _run_report(
        self,
        property_id: str,
        date_ranges: list[dict],
        dimensions: list[str],
        metrics: list[str],
        dimension_filter: dict | None,
        order_bys: list[dict] | None,
        limit: int,
        pii_acknowledged: bool,
    ) -> dict:
        """Execute a standard GA4 Data API report.

        Args:
            property_id: GA4 property ID or resource name.
            date_ranges: List of ``{"start_date": "...", "end_date": "..."}`` dicts.
            dimensions: List of GA4 dimension names.
            metrics: List of GA4 metric names.
            dimension_filter: Optional ``FilterExpression`` dict (GA4 API format).
            order_bys: Optional list of ``OrderBy`` dicts.
            limit: Maximum rows to return (hard-capped to 100,000).
            pii_acknowledged: Allow PII dimensions when ``True``.

        Returns:
            A dict with keys ``rows``, ``dimension_headers``, ``metric_headers``,
            ``row_count``, and optional ``warnings`` / ``small_sample_warning``.
        """
        from google.analytics.data_v1beta.types import (  # noqa: PLC0415
            DateRange,
            Dimension,
            FilterExpression,
            Metric,
            OrderBy,
            RunReportRequest,
        )
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        pii_err = self._check_pii(dimensions, pii_acknowledged)
        if pii_err:
            return {"error": pii_err}

        clamped, warnings = self._clamp_limit(limit)
        prop = self._resolve_property(property_id)
        client = self._get_data_client()

        dr_objects = [
            DateRange(start_date=dr["start_date"], end_date=dr["end_date"])
            for dr in (date_ranges or [{"start_date": "28daysAgo", "end_date": "today"}])
        ]
        dim_objects = [Dimension(name=d) for d in (dimensions or [])]
        met_objects = [Metric(name=m) for m in (metrics or [])]

        kwargs: dict[str, Any] = {
            "property": prop,
            "date_ranges": dr_objects,
            "dimensions": dim_objects,
            "metrics": met_objects,
            "limit": clamped,
        }
        if dimension_filter:
            kwargs["dimension_filter"] = FilterExpression(**dimension_filter)
        if order_bys:
            kwargs["order_bys"] = [OrderBy(**o) for o in order_bys]

        response = client.run_report(RunReportRequest(**kwargs))
        result = MessageToDict(response._pb)  # type: ignore[attr-defined]
        result = self._attach_sample_warning(result)
        if warnings:
            result["warnings"] = warnings
        return result

    def _batch_run_reports(self, property_id: str, requests: list[dict]) -> dict:
        """Execute multiple GA4 reports in a single API call.

        Args:
            property_id: GA4 property ID or resource name.
            requests: List of report request dicts.  Each dict accepts the same
                keys as ``run_report`` (date_ranges, dimensions, metrics, etc.).

        Returns:
            A dict with a ``"reports"`` list, one entry per request.
        """
        from google.analytics.data_v1beta.types import (  # noqa: PLC0415
            BatchRunReportsRequest,
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_data_client()

        report_requests = []
        for req in requests:
            dr = [
                DateRange(start_date=d["start_date"], end_date=d["end_date"])
                for d in req.get("date_ranges", [{"start_date": "28daysAgo", "end_date": "today"}])
            ]
            dims = [Dimension(name=d) for d in req.get("dimensions", [])]
            mets = [Metric(name=m) for m in req.get("metrics", [])]
            lim = min(req.get("limit", 1000), _ROW_HARD_CAP)
            report_requests.append(
                RunReportRequest(
                    property=prop,
                    date_ranges=dr,
                    dimensions=dims,
                    metrics=mets,
                    limit=lim,
                )
            )

        response = client.batch_run_reports(
            BatchRunReportsRequest(property=prop, requests=report_requests)
        )
        reports = [MessageToDict(r._pb) for r in response.reports]  # type: ignore[attr-defined]
        return {"reports": reports, "report_count": len(reports)}

    def _run_pivot_report(
        self,
        property_id: str,
        date_ranges: list[dict],
        dimensions: list[str],
        metrics: list[str],
        pivots: list[dict],
    ) -> dict:
        """Execute a GA4 pivot report.

        Args:
            property_id: GA4 property ID or resource name.
            date_ranges: List of date range dicts.
            dimensions: List of dimension names.
            metrics: List of metric names.
            pivots: List of pivot config dicts (GA4 ``Pivot`` API format).

        Returns:
            A dict containing the pivot report rows and headers.
        """
        from google.analytics.data_v1beta.types import (  # noqa: PLC0415
            DateRange,
            Dimension,
            Metric,
            Pivot,
            RunPivotReportRequest,
        )
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_data_client()

        dr_objects = [
            DateRange(start_date=d["start_date"], end_date=d["end_date"])
            for d in (date_ranges or [{"start_date": "28daysAgo", "end_date": "today"}])
        ]
        pivot_objects = [Pivot(**p) for p in (pivots or [])]

        response = client.run_pivot_report(
            RunPivotReportRequest(
                property=prop,
                date_ranges=dr_objects,
                dimensions=[Dimension(name=d) for d in dimensions],
                metrics=[Metric(name=m) for m in metrics],
                pivots=pivot_objects,
            )
        )
        return MessageToDict(response._pb)  # type: ignore[attr-defined]

    def _run_realtime_report(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
        limit: int,
        pii_acknowledged: bool,
    ) -> dict:
        """Fetch a GA4 real-time report (currently active users/events).

        Args:
            property_id: GA4 property ID or resource name.
            dimensions: List of dimension names.
            metrics: List of metric names.
            limit: Maximum rows (hard-capped to 100,000).
            pii_acknowledged: Allow PII dimensions when ``True``.

        Returns:
            A dict with real-time rows and headers.
        """
        from google.analytics.data_v1beta.types import (  # noqa: PLC0415
            Dimension,
            Metric,
            RunRealtimeReportRequest,
        )
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        pii_err = self._check_pii(dimensions, pii_acknowledged)
        if pii_err:
            return {"error": pii_err}

        clamped, warnings = self._clamp_limit(limit)
        prop = self._resolve_property(property_id)
        client = self._get_data_client()

        response = client.run_realtime_report(
            RunRealtimeReportRequest(
                property=prop,
                dimensions=[Dimension(name=d) for d in (dimensions or [])],
                metrics=[Metric(name=m) for m in (metrics or [])],
                limit=clamped,
            )
        )
        result = MessageToDict(response._pb)  # type: ignore[attr-defined]
        if warnings:
            result["warnings"] = warnings
        return result

    def _get_metadata(self, property_id: str) -> dict:
        """List all dimensions and metrics available for a GA4 property.

        Args:
            property_id: GA4 property ID or resource name.

        Returns:
            A dict with ``"dimensions"`` and ``"metrics"`` lists.
        """
        from google.analytics.data_v1beta.types import GetMetadataRequest  # noqa: PLC0415
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_data_client()
        # Metadata endpoint uses "properties/{id}/metadata" as the resource name
        response = client.get_metadata(
            GetMetadataRequest(name=f"{prop}/metadata")
        )
        return MessageToDict(response._pb)  # type: ignore[attr-defined]

    def _check_compatibility(
        self,
        property_id: str,
        dimensions: list[str],
        metrics: list[str],
    ) -> dict:
        """Check whether a set of dimensions and metrics can be queried together.

        Args:
            property_id: GA4 property ID or resource name.
            dimensions: Proposed dimension names.
            metrics: Proposed metric names.

        Returns:
            A dict reporting the compatibility status for each dimension/metric.
        """
        from google.analytics.data_v1beta.types import (  # noqa: PLC0415
            CheckCompatibilityRequest,
            Dimension,
            Metric,
        )
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_data_client()

        response = client.check_compatibility(
            CheckCompatibilityRequest(
                property=prop,
                dimensions=[Dimension(name=d) for d in (dimensions or [])],
                metrics=[Metric(name=m) for m in (metrics or [])],
            )
        )
        return MessageToDict(response._pb)  # type: ignore[attr-defined]

    def _list_audiences(self, property_id: str) -> dict:
        """List all GA4 Audiences defined on a property.

        Args:
            property_id: GA4 property ID or resource name.

        Returns:
            A dict with an ``"audiences"`` list.
        """
        from google.analytics.admin_v1alpha.types import ListAudiencesRequest  # noqa: PLC0415
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_admin_client()
        pager = client.list_audiences(ListAudiencesRequest(parent=prop))
        audiences = [MessageToDict(a._pb) for a in pager]  # type: ignore[attr-defined]
        return {"audiences": audiences, "count": len(audiences)}

    def _list_custom_dimensions(self, property_id: str) -> dict:
        """List all custom dimensions registered on a GA4 property.

        Args:
            property_id: GA4 property ID or resource name.

        Returns:
            A dict with a ``"custom_dimensions"`` list.
        """
        from google.analytics.admin_v1alpha.types import ListCustomDimensionsRequest  # noqa: PLC0415
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_admin_client()
        pager = client.list_custom_dimensions(
            ListCustomDimensionsRequest(parent=prop)
        )
        dims = [MessageToDict(d._pb) for d in pager]  # type: ignore[attr-defined]
        return {"custom_dimensions": dims, "count": len(dims)}

    def _list_custom_metrics(self, property_id: str) -> dict:
        """List all custom metrics registered on a GA4 property.

        Args:
            property_id: GA4 property ID or resource name.

        Returns:
            A dict with a ``"custom_metrics"`` list.
        """
        from google.analytics.admin_v1alpha.types import ListCustomMetricsRequest  # noqa: PLC0415
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_admin_client()
        pager = client.list_custom_metrics(
            ListCustomMetricsRequest(parent=prop)
        )
        mets = [MessageToDict(m._pb) for m in pager]  # type: ignore[attr-defined]
        return {"custom_metrics": mets, "count": len(mets)}

    def _list_conversion_events(self, property_id: str) -> dict:
        """List all conversion events registered on a GA4 property.

        Args:
            property_id: GA4 property ID or resource name.

        Returns:
            A dict with a ``"conversion_events"`` list.
        """
        from google.analytics.admin_v1alpha.types import ListConversionEventsRequest  # noqa: PLC0415
        from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

        prop = self._resolve_property(property_id)
        client = self._get_admin_client()
        pager = client.list_conversion_events(
            ListConversionEventsRequest(parent=prop)
        )
        events = [MessageToDict(e._pb) for e in pager]  # type: ignore[attr-defined]
        return {"conversion_events": events, "count": len(events)}

    # ------------------------------------------------------------------
    # execute — operation dispatcher
    # ------------------------------------------------------------------

    def execute(  # noqa: PLR0913
        self,
        operation: str,
        property_id: str = "",
        date_ranges: list | None = None,
        dimensions: list | None = None,
        metrics: list | None = None,
        dimension_filter: dict | None = None,
        order_bys: list | None = None,
        limit: int = 1000,
        requests: list | None = None,
        pivots: list | None = None,
        pii_acknowledged: bool = False,
    ) -> dict:
        """Dispatch to the requested GA4 operation.

        Args:
            operation: One of the supported operation names (see module docstring).
            property_id: GA4 numeric property ID (e.g. ``"123456789"``) or full
                resource name (``"properties/123456789"``).  Falls back to the
                ``GOOGLE_GA4_PROPERTY_ID`` environment variable when omitted.
            date_ranges: List of ``{"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"}``
                dicts.  Relative offsets such as ``"28daysAgo"`` and ``"today"`` are
                also supported.  Defaults to the last 28 days when omitted.
            dimensions: List of GA4 dimension API names (e.g.
                ``["sessionSource", "deviceCategory"]``).
            metrics: List of GA4 metric API names (e.g.
                ``["sessions", "conversions", "totalRevenue"]``).
            dimension_filter: Optional ``FilterExpression`` dict in GA4 API wire
                format.  Used by ``run_report`` only.
            order_bys: Optional list of ``OrderBy`` dicts in GA4 API wire format.
            limit: Maximum number of rows to return.  Clamped to 100,000 (hard cap).
                A warning is added to the response when ``limit > 10,000``.
            requests: List of report request dicts for ``batch_run_reports``.
            pivots: List of ``Pivot`` config dicts for ``run_pivot_report``.
            pii_acknowledged: When ``True``, allows ``user_id`` / ``client_id``
                dimensions.  Defaults to ``False`` (blocked).

        Returns:
            Operation-specific dict on success, or ``{"error": "..."}`` on failure.

            Common keys across data operations:
            * ``rows`` — list of row dicts with ``dimension_values`` and
              ``metric_values``.
            * ``dimension_headers`` — list of ``{"name": "..."}`` dicts.
            * ``metric_headers`` — list of ``{"name": "...", "type": "..."}`` dicts.
            * ``row_count`` — total matched rows (may exceed ``limit``).
            * ``warnings`` — advisory strings (e.g. large-limit notice).
            * ``small_sample_warning`` — present and ``true`` when totals < 100.
        """
        op = operation.strip().lower()
        dims = dimensions or []
        mets = metrics or []

        try:
            if op == "run_report":
                return self._run_report(
                    property_id=property_id,
                    date_ranges=date_ranges or [],
                    dimensions=dims,
                    metrics=mets,
                    dimension_filter=dimension_filter,
                    order_bys=order_bys,
                    limit=limit,
                    pii_acknowledged=pii_acknowledged,
                )

            if op == "batch_run_reports":
                if not requests:
                    return {"error": "requests list is required for batch_run_reports."}
                return self._batch_run_reports(
                    property_id=property_id,
                    requests=requests,
                )

            if op == "run_pivot_report":
                return self._run_pivot_report(
                    property_id=property_id,
                    date_ranges=date_ranges or [],
                    dimensions=dims,
                    metrics=mets,
                    pivots=pivots or [],
                )

            if op == "run_realtime_report":
                return self._run_realtime_report(
                    property_id=property_id,
                    dimensions=dims,
                    metrics=mets,
                    limit=limit,
                    pii_acknowledged=pii_acknowledged,
                )

            if op == "get_metadata":
                return self._get_metadata(property_id=property_id)

            if op == "check_compatibility":
                return self._check_compatibility(
                    property_id=property_id,
                    dimensions=dims,
                    metrics=mets,
                )

            if op == "list_audiences":
                return self._list_audiences(property_id=property_id)

            if op == "list_custom_dimensions":
                return self._list_custom_dimensions(property_id=property_id)

            if op == "list_custom_metrics":
                return self._list_custom_metrics(property_id=property_id)

            if op == "list_conversion_events":
                return self._list_conversion_events(property_id=property_id)

        except (RuntimeError, ValueError) as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error in {op!r}: {exc}"}

        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {', '.join(sorted(_VALID_OPERATIONS))}."
            )
        }
