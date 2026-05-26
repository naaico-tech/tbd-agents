"""GoogleAdsPlugin — Google Ads API (GAQL) integration for tbd-agents.

Provides read-only access to Google Ads accounts via the ``google-ads`` Python
library and GAQL (Google Ads Query Language).  All operations are strictly
non-destructive; no campaign changes, bid adjustments, or budget modifications
are made.

Supported operations
--------------------
``query``
    Run an arbitrary GAQL ``SELECT`` statement against a customer account.
``list_campaigns``
    List campaigns for a customer, optionally filtered by status.
``campaign_performance``
    Retrieve key performance metrics for all campaigns over a date range.
``keyword_performance``
    Retrieve keyword-level performance for a campaign over a date range.
``ad_group_performance``
    Retrieve ad-group-level performance for a campaign.
``list_accessible_customers``
    List all customer accounts accessible to the authenticated login customer.
``search_terms_report``
    Retrieve search-term performance data for a campaign.
``change_history``
    Retrieve the change-history log for an account over a date range.

Authentication
--------------
Requires a developer token and OAuth2 refresh-token credentials.  All five
values are resolved from environment variables populated via ``env_config``:

- ``GOOGLE_ADS_DEVELOPER_TOKEN``
- ``GOOGLE_ADS_CLIENT_ID``
- ``GOOGLE_ADS_CLIENT_SECRET``
- ``GOOGLE_ADS_REFRESH_TOKEN``
- ``GOOGLE_ADS_LOGIN_CUSTOMER_ID``

The ``google-ads`` client is instantiated lazily on first use.
"""

from __future__ import annotations

import os
import re
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Maximum number of rows returned by a single GAQL query call.
_GAQL_ROW_LIMIT = 10_000

#: Allowlisted GAQL statement prefix — only SELECT queries are permitted.
_SELECT_RE = re.compile(r"^\s*SELECT\b", re.IGNORECASE)

#: All supported operations.
_VALID_OPERATIONS = {
    "query",
    "list_campaigns",
    "campaign_performance",
    "keyword_performance",
    "ad_group_performance",
    "list_accessible_customers",
    "search_terms_report",
    "change_history",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class GoogleAdsPlugin(PluginBase):
    """Google Ads API plugin for the Marketing Analyst agent.

    All database-modifying GAQL statements are rejected before any network call
    is made.  Only ``SELECT …`` queries are allowed.  The Google Ads client is
    built lazily from environment variables on each call so credentials can be
    rotated without restarting the process.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "google_ads"

    @property
    def description(self) -> str:
        return (
            "Read-only access to Google Ads via GAQL. Supported operations: "
            "query (run arbitrary GAQL SELECT), list_campaigns (campaigns by "
            "status), campaign_performance (impressions/clicks/cost/conversions "
            "over a date range), keyword_performance (keyword-level stats), "
            "ad_group_performance (ad-group-level stats), "
            "list_accessible_customers (list available accounts), "
            "search_terms_report (search-term match data), "
            "change_history (account mutation log). "
            "Only SELECT queries are allowed — no writes."
        )

    @property
    def tags(self) -> list[str]:
        return [
            "google_ads",
            "ads",
            "paid-search",
            "analytics",
            "marketing",
            "read",
        ]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "GOOGLE_ADS_DEVELOPER_TOKEN": "{{token:google-ads-developer-token}}",
            "GOOGLE_ADS_CLIENT_ID": "{{token:google-ads-client-id}}",
            "GOOGLE_ADS_CLIENT_SECRET": "{{token:google-ads-client-secret}}",
            "GOOGLE_ADS_REFRESH_TOKEN": "{{token:google-ads-refresh-token}}",
            "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "{{token:google-ads-login-customer-id}}",
        }

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Build and return an authenticated ``GoogleAdsClient``.

        Configuration is assembled from environment variables and passed to
        ``GoogleAdsClient.load_from_dict``.

        Returns:
            A configured ``google.ads.googleads.client.GoogleAdsClient`` instance.

        Raises:
            RuntimeError: If any required environment variable is missing.
        """
        from google.ads.googleads.client import GoogleAdsClient  # noqa: PLC0415

        required = {
            "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
            "client_id": "GOOGLE_ADS_CLIENT_ID",
            "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
            "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
        }
        config: dict[str, Any] = {}
        missing = []
        for key, env_var in required.items():
            val = os.environ.get(env_var, "").strip()
            if not val:
                missing.append(env_var)
            else:
                config[key] = val

        login_cid = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
        if login_cid:
            config["login_customer_id"] = login_cid.replace("-", "")

        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        config["use_proto_plus"] = True
        return GoogleAdsClient.load_from_dict(config)

    # ------------------------------------------------------------------
    # Safety helpers
    # ------------------------------------------------------------------

    def _validate_gaql(self, gaql: str) -> str | None:
        """Return an error string if *gaql* is not a safe SELECT statement.

        Args:
            gaql: The GAQL query string provided by the caller.

        Returns:
            An error message string, or ``None`` if the query is safe.
        """
        stripped = gaql.strip()
        if not stripped:
            return "gaql query must not be empty."
        if not _SELECT_RE.match(stripped):
            return (
                "Only SELECT queries are permitted. "
                f"Query starts with: {stripped[:60]!r}"
            )
        return None

    def _normalise_customer_id(self, customer_id: str) -> str:
        """Strip hyphens from a customer ID (e.g. ``123-456-7890`` → ``1234567890``)."""
        return customer_id.replace("-", "").strip()

    # ------------------------------------------------------------------
    # Row serialisation
    # ------------------------------------------------------------------

    def _row_to_dict(self, row: Any) -> dict:
        """Convert a ``google-ads`` proto-plus Row object to a plain dict.

        Args:
            row: A proto-plus Row object from the Google Ads API response.

        Returns:
            A JSON-serialisable dict representation of the row.
        """
        try:
            # proto-plus objects expose __class__ with a to_json method via
            # the proto package; fall back to string repr on failure.
            import proto  # noqa: PLC0415

            return type(row).to_dict(row)
        except Exception:  # noqa: BLE001
            return {"raw": str(row)}

    # ------------------------------------------------------------------
    # Operation handlers
    # ------------------------------------------------------------------

    def _query(self, customer_id: str, gaql: str) -> dict:
        """Execute a raw GAQL SELECT query against a customer account.

        Args:
            customer_id: Google Ads customer ID (with or without hyphens).
            gaql: A valid GAQL ``SELECT`` statement.

        Returns:
            A dict with ``"rows"`` (list of row dicts) and ``"row_count"``.
        """
        err = self._validate_gaql(gaql)
        if err:
            return {"error": err}

        cid = self._normalise_customer_id(customer_id)
        client = self._get_client()
        service = client.get_service("GoogleAdsService")
        response = service.search(customer_id=cid, query=gaql)
        rows = [self._row_to_dict(row) for row in response]
        return {"rows": rows, "row_count": len(rows)}

    def _list_campaigns(self, customer_id: str, status: str) -> dict:
        """List campaigns for a customer, optionally filtered by status.

        Args:
            customer_id: Google Ads customer ID.
            status: Campaign status filter, e.g. ``"ENABLED"``, ``"PAUSED"``,
                ``"REMOVED"``.  Pass an empty string for all statuses.

        Returns:
            A dict with a ``"campaigns"`` list.
        """
        status_clause = ""
        if status.strip():
            status_clause = f" AND campaign.status = '{status.strip().upper()}'"

        gaql = (
            "SELECT campaign.id, campaign.name, campaign.status, "
            "campaign.advertising_channel_type, campaign.start_date, "
            "campaign.end_date, campaign_budget.amount_micros "
            "FROM campaign "
            f"WHERE campaign.status != 'REMOVED'{status_clause} "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        result = self._query(customer_id, gaql)
        if "error" in result:
            return result
        return {"campaigns": result["rows"], "count": result["row_count"]}

    def _campaign_performance(
        self,
        customer_id: str,
        date_from: str,
        date_to: str,
        metrics: list[str],
    ) -> dict:
        """Retrieve campaign performance metrics over a date range.

        Args:
            customer_id: Google Ads customer ID.
            date_from: Start date in ``YYYY-MM-DD`` format.
            date_to: End date in ``YYYY-MM-DD`` format.
            metrics: List of GAQL metric field names.  Defaults to a standard
                set (impressions, clicks, cost, conversions, ROAS) when empty.

        Returns:
            A dict with a ``"rows"`` list, one entry per campaign per date.
        """
        default_metrics = [
            "metrics.impressions",
            "metrics.clicks",
            "metrics.cost_micros",
            "metrics.conversions",
            "metrics.conversions_value",
            "metrics.ctr",
            "metrics.average_cpc",
        ]
        selected_metrics = metrics if metrics else default_metrics
        metric_str = ", ".join(selected_metrics)

        gaql = (
            f"SELECT campaign.id, campaign.name, campaign.status, {metric_str} "
            "FROM campaign "
            f"WHERE segments.date BETWEEN '{date_from}' AND '{date_to}' "
            "AND campaign.status != 'REMOVED' "
            f"ORDER BY metrics.cost_micros DESC "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        return self._query(customer_id, gaql)

    def _keyword_performance(
        self,
        customer_id: str,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> dict:
        """Retrieve keyword-level performance for a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign resource ID or numeric ID.
            date_from: Start date in ``YYYY-MM-DD`` format.
            date_to: End date in ``YYYY-MM-DD`` format.

        Returns:
            A dict with a ``"rows"`` list of keyword stats.
        """
        campaign_clause = ""
        if campaign_id.strip():
            campaign_clause = f" AND campaign.id = {campaign_id.strip()}"

        gaql = (
            "SELECT ad_group_criterion.keyword.text, "
            "ad_group_criterion.keyword.match_type, "
            "ad_group_criterion.status, "
            "campaign.id, campaign.name, "
            "ad_group.id, ad_group.name, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.average_cpc, metrics.quality_score "
            "FROM keyword_view "
            f"WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'"
            f"{campaign_clause} "
            "AND ad_group_criterion.status != 'REMOVED' "
            f"ORDER BY metrics.cost_micros DESC "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        return self._query(customer_id, gaql)

    def _ad_group_performance(self, customer_id: str, campaign_id: str) -> dict:
        """Retrieve ad-group-level performance for a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign resource ID or numeric ID.  Pass empty string
                to fetch all ad groups across the account.

        Returns:
            A dict with a ``"rows"`` list of ad-group stats.
        """
        campaign_clause = ""
        if campaign_id.strip():
            campaign_clause = f" AND campaign.id = {campaign_id.strip()}"

        gaql = (
            "SELECT ad_group.id, ad_group.name, ad_group.status, "
            "campaign.id, campaign.name, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.ctr, metrics.average_cpc "
            "FROM ad_group "
            f"WHERE ad_group.status != 'REMOVED'{campaign_clause} "
            f"ORDER BY metrics.cost_micros DESC "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        return self._query(customer_id, gaql)

    def _list_accessible_customers(self) -> dict:
        """List all Google Ads customer accounts accessible to the login customer.

        Returns:
            A dict with a ``"customer_ids"`` list of account resource names.
        """
        from google.ads.googleads.client import GoogleAdsClient  # noqa: PLC0415

        client = self._get_client()
        service = client.get_service("CustomerService")
        response = service.list_accessible_customers()
        return {
            "customer_resource_names": list(response.resource_names),
            "count": len(response.resource_names),
        }

    def _search_terms_report(
        self,
        customer_id: str,
        campaign_id: str,
        date_from: str,
        date_to: str,
    ) -> dict:
        """Retrieve search-term match performance for a campaign.

        Args:
            customer_id: Google Ads customer ID.
            campaign_id: Campaign numeric ID.
            date_from: Start date in ``YYYY-MM-DD`` format.
            date_to: End date in ``YYYY-MM-DD`` format.

        Returns:
            A dict with a ``"rows"`` list of search-term stats.
        """
        campaign_clause = ""
        if campaign_id.strip():
            campaign_clause = f" AND campaign.id = {campaign_id.strip()}"

        gaql = (
            "SELECT search_term_view.search_term, "
            "search_term_view.status, "
            "campaign.id, campaign.name, "
            "ad_group.id, ad_group.name, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.ctr "
            "FROM search_term_view "
            f"WHERE segments.date BETWEEN '{date_from}' AND '{date_to}'"
            f"{campaign_clause} "
            f"ORDER BY metrics.cost_micros DESC "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        return self._query(customer_id, gaql)

    def _change_history(
        self, customer_id: str, date_from: str, date_to: str
    ) -> dict:
        """Retrieve the account change-history log over a date range.

        Args:
            customer_id: Google Ads customer ID.
            date_from: Start date in ``YYYY-MM-DD`` format.
            date_to: End date in ``YYYY-MM-DD`` format.

        Returns:
            A dict with a ``"rows"`` list of change-history entries.
        """
        gaql = (
            "SELECT change_event.change_date_time, "
            "change_event.change_resource_type, "
            "change_event.change_resource_name, "
            "change_event.changed_fields, "
            "change_event.client_type, "
            "change_event.user_email "
            "FROM change_event "
            f"WHERE change_event.change_date_time >= '{date_from} 00:00:00' "
            f"AND change_event.change_date_time <= '{date_to} 23:59:59' "
            f"ORDER BY change_event.change_date_time DESC "
            f"LIMIT {_GAQL_ROW_LIMIT}"
        )
        return self._query(customer_id, gaql)

    # ------------------------------------------------------------------
    # execute — operation dispatcher
    # ------------------------------------------------------------------

    def execute(  # noqa: PLR0913
        self,
        operation: str,
        customer_id: str = "",
        gaql: str = "",
        status: str = "",
        date_from: str = "",
        date_to: str = "",
        metrics: list | None = None,
        campaign_id: str = "",
    ) -> dict:
        """Dispatch to the requested Google Ads operation.

        Args:
            operation: One of the supported operation names (see module docstring).
            customer_id: Google Ads customer (account) ID, e.g. ``"123-456-7890"``
                or ``"1234567890"``.  Not required for ``list_accessible_customers``.
            gaql: A GAQL ``SELECT`` statement.  Required for ``query``.
            status: Campaign status filter for ``list_campaigns``.  One of
                ``"ENABLED"``, ``"PAUSED"``, ``"REMOVED"``, or empty for all.
            date_from: Start date in ``YYYY-MM-DD`` format.  Required by
                ``campaign_performance``, ``keyword_performance``,
                ``search_terms_report``, and ``change_history``.
            date_to: End date in ``YYYY-MM-DD`` format.  Same as ``date_from``.
            metrics: List of GAQL metric field names for ``campaign_performance``.
                Defaults to a standard set when omitted.
            campaign_id: Campaign numeric ID for ``keyword_performance``,
                ``ad_group_performance``, and ``search_terms_report``.

        Returns:
            Operation-specific dict on success, or ``{"error": "..."}`` on failure.
        """
        op = operation.strip().lower()

        try:
            if op == "query":
                if not gaql.strip():
                    return {"error": "gaql is required for the query operation."}
                return self._query(customer_id, gaql)

            if op == "list_campaigns":
                return self._list_campaigns(customer_id, status)

            if op == "campaign_performance":
                return self._campaign_performance(
                    customer_id, date_from, date_to, metrics or []
                )

            if op == "keyword_performance":
                return self._keyword_performance(
                    customer_id, campaign_id, date_from, date_to
                )

            if op == "ad_group_performance":
                return self._ad_group_performance(customer_id, campaign_id)

            if op == "list_accessible_customers":
                return self._list_accessible_customers()

            if op == "search_terms_report":
                return self._search_terms_report(
                    customer_id, campaign_id, date_from, date_to
                )

            if op == "change_history":
                return self._change_history(customer_id, date_from, date_to)

        except RuntimeError as exc:
            return {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Unexpected error in {op!r}: {exc}"}

        return {
            "error": (
                f"Unsupported operation: {operation!r}. "
                f"Valid operations: {', '.join(sorted(_VALID_OPERATIONS))}."
            )
        }
