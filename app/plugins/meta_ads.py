"""MetaAdsPlugin — Meta (Facebook/Instagram) Marketing API for tbd-agents.

Provides read-only access to Meta Ads Manager via the Meta Graph API v20.0.
All HTTP calls are made with the ``requests`` library (lazily imported) and
authenticated via a long-lived User or System User access token stored in
``META_ADS_ACCESS_TOKEN``.

Supported operations
--------------------
``list_accounts``
    List all ad accounts accessible to the authenticated user.
``list_campaigns``
    List campaigns for an ad account, optionally filtered by status.
``campaign_insights``
    Fetch performance insights for a campaign with optional breakdowns.
``adset_insights``
    Fetch performance insights for an ad set.
``ad_insights``
    Fetch performance insights for a single ad.
``account_insights``
    Fetch account-level aggregate insights with optional breakdowns.
``list_creatives``
    List ad creatives for an account.
``audience_estimate``
    Estimate the potential reach for a targeting spec.

Authentication
--------------
All requests include the ``access_token`` as a query parameter.  The optional
``META_ADS_APP_SECRET`` is available for server-side request signing when
required by the app configuration (not applied automatically here; callers may
use it to generate appsecret_proof if their app requires it).

API base URL: ``https://graph.facebook.com/v20.0/``

Rate-limiting note
------------------
The Meta Marketing API uses Business Use Case (BUC) rate limits.  This plugin
does not implement automatic retry/back-off; callers should handle
``"error": {"code": 17, ...}`` responses by waiting and retrying.
"""

from __future__ import annotations

import os
from typing import Any

from app.core.plugin_base import PluginBase

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_API_BASE = "https://graph.facebook.com/v20.0"

#: Default fields returned for campaign and account insights.
_DEFAULT_INSIGHT_FIELDS = [
    "impressions",
    "clicks",
    "spend",
    "reach",
    "ctr",
    "cpc",
    "cpm",
    "actions",
    "conversions",
    "cost_per_action_type",
    "purchase_roas",
]

#: Default fields returned for ad-set and ad insights.
_DEFAULT_AD_FIELDS = [
    "impressions",
    "clicks",
    "spend",
    "reach",
    "ctr",
    "cpc",
    "cpm",
    "actions",
    "cost_per_action_type",
]

#: Supported date_preset values (Meta API).
_DATE_PRESETS = {
    "today",
    "yesterday",
    "this_week_sun_today",
    "this_week_mon_today",
    "last_week_sun_sat",
    "last_week_mon_sun",
    "last_3d",
    "last_7d",
    "last_14d",
    "last_28d",
    "last_30d",
    "last_90d",
    "this_month",
    "last_month",
    "this_quarter",
    "maximum",
}

#: All supported operations.
_VALID_OPERATIONS = {
    "list_accounts",
    "list_campaigns",
    "campaign_insights",
    "adset_insights",
    "ad_insights",
    "account_insights",
    "list_creatives",
    "audience_estimate",
}


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------


class MetaAdsPlugin(PluginBase):
    """Meta (Facebook / Instagram) Marketing API plugin for the Marketing Analyst agent.

    All operations are read-only.  Ad budgets, targeting, creatives, and
    campaign statuses are never modified.  The ``requests`` library is imported
    lazily inside helper methods to avoid import-time failures when the package
    is not installed.
    """

    # ------------------------------------------------------------------
    # PluginBase interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "meta_ads"

    @property
    def description(self) -> str:
        return (
            "Read-only access to Meta (Facebook/Instagram) Ads Manager via the "
            "Graph API v20.0. Supported operations: list_accounts (ad accounts), "
            "list_campaigns (campaigns by status), campaign_insights (performance "
            "metrics with breakdowns), adset_insights (ad-set level stats), "
            "ad_insights (single ad stats), account_insights (account aggregate), "
            "list_creatives (ad creative library), audience_estimate (reach "
            "estimate for a targeting spec). "
            "All operations are strictly read-only."
        )

    @property
    def tags(self) -> list[str]:
        return [
            "meta_ads",
            "facebook_ads",
            "instagram_ads",
            "ads",
            "social-ads",
            "analytics",
            "marketing",
            "read",
        ]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "META_ADS_ACCESS_TOKEN": "{{token:meta-ads-access-token}}",
            "META_ADS_APP_SECRET": "{{token:meta-ads-app-secret}}",
        }

    # ------------------------------------------------------------------
    # Auth / HTTP helpers
    # ------------------------------------------------------------------

    def _token(self) -> str:
        """Read and return the Meta access token from the environment.

        Returns:
            The access token string.

        Raises:
            RuntimeError: If ``META_ADS_ACCESS_TOKEN`` is unset or empty.
        """
        token = os.environ.get("META_ADS_ACCESS_TOKEN", "").strip()
        if not token:
            raise RuntimeError(
                "META_ADS_ACCESS_TOKEN environment variable is not set."
            )
        return token

    def _get(self, path: str, params: dict | None = None) -> dict:
        """Perform a GET request against the Meta Graph API.

        Args:
            path: The API path (e.g. ``"/me/adaccounts"``).  Leading slash is
                optional — it is normalised automatically.
            params: Additional query parameters.  ``access_token`` is always
                injected automatically.

        Returns:
            The parsed JSON response body as a dict.

        Raises:
            RuntimeError: If the HTTP response status is not 200 or the body
                contains a top-level ``"error"`` key from the Meta API.
        """
        import requests  # noqa: PLC0415

        url = f"{_API_BASE}/{path.lstrip('/')}"
        query: dict[str, Any] = {"access_token": self._token()}
        if params:
            query.update(params)

        response = requests.get(url, params=query, timeout=30)
        data = response.json()

        if response.status_code != 200 or "error" in data:
            meta_err = data.get("error", {})
            raise RuntimeError(
                f"Meta API error {meta_err.get('code', response.status_code)}: "
                f"{meta_err.get('message', response.text)}"
            )
        return data

    def _post(self, path: str, payload: dict | None = None) -> dict:
        """Perform a POST request against the Meta Graph API.

        Used only for ``audience_estimate``, which uses a POST to the
        ``/reachestimate`` endpoint.

        Args:
            path: The API path.
            payload: POST body parameters.

        Returns:
            The parsed JSON response body as a dict.

        Raises:
            RuntimeError: On HTTP or Meta API errors.
        """
        import requests  # noqa: PLC0415

        url = f"{_API_BASE}/{path.lstrip('/')}"
        data: dict[str, Any] = {"access_token": self._token()}
        if payload:
            data.update(payload)

        response = requests.post(url, data=data, timeout=30)
        body = response.json()

        if response.status_code not in (200, 201) or "error" in body:
            meta_err = body.get("error", {})
            raise RuntimeError(
                f"Meta API error {meta_err.get('code', response.status_code)}: "
                f"{meta_err.get('message', response.text)}"
            )
        return body

    def _paginate(self, initial_data: dict, max_pages: int = 5) -> list[dict]:
        """Follow Meta pagination cursors and aggregate results.

        Args:
            initial_data: The first API response (must contain ``"data"`` key).
            max_pages: Maximum additional pages to fetch (default 5).

        Returns:
            A flat list of all ``data`` items across pages.
        """
        import requests  # noqa: PLC0415

        items: list[dict] = list(initial_data.get("data", []))
        paging = initial_data.get("paging", {})
        next_url = paging.get("next")
        pages = 0

        while next_url and pages < max_pages:
            resp = requests.get(next_url, timeout=30)
            page = resp.json()
            items.extend(page.get("data", []))
            paging = page.get("paging", {})
            next_url = paging.get("next")
            pages += 1

        return items

    def _build_date_params(
        self,
        date_preset: str,
        time_range: dict | None,
    ) -> dict:
        """Build Meta API date parameters from preset or explicit range.

        Args:
            date_preset: A Meta ``date_preset`` string (e.g. ``"last_30d"``).
            time_range: A ``{"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"}`` dict.

        Returns:
            A dict with either ``date_preset`` or ``time_range`` populated, or
            an empty dict when neither is supplied (defaults to ``last_30d``).
        """
        import json as _json  # noqa: PLC0415

        if time_range and ("since" in time_range or "until" in time_range):
            return {"time_range": _json.dumps(time_range)}
        preset = date_preset.strip() if date_preset else ""
        if preset and preset in _DATE_PRESETS:
            return {"date_preset": preset}
        # Default fallback
        return {"date_preset": "last_30d"}

    # ------------------------------------------------------------------
    # Operation handlers
    # ------------------------------------------------------------------

    def _list_accounts(self) -> dict:
        """List all ad accounts accessible to the authenticated user.

        Returns:
            A dict with an ``"accounts"`` list of account summaries.
        """
        data = self._get(
            "/me/adaccounts",
            params={"fields": "id,name,currency,timezone_name,account_status,spend_cap"},
        )
        accounts = self._paginate(data)
        return {"accounts": accounts, "count": len(accounts)}

    def _list_campaigns(self, account_id: str, status: str) -> dict:
        """List campaigns for an ad account.

        Args:
            account_id: Meta ad account ID (e.g. ``"act_123456789"``).
            status: Filter by effective status.  One of ``"ACTIVE"``,
                ``"PAUSED"``, ``"ARCHIVED"``, or empty for all.

        Returns:
            A dict with a ``"campaigns"`` list.
        """
        params: dict[str, Any] = {
            "fields": "id,name,status,objective,daily_budget,lifetime_budget,"
                      "start_time,stop_time,created_time",
        }
        if status.strip():
            params["effective_status"] = f'["{status.strip().upper()}"]'

        aid = self._normalise_account_id(account_id)
        data = self._get(f"/{aid}/campaigns", params=params)
        campaigns = self._paginate(data)
        return {"campaigns": campaigns, "count": len(campaigns)}

    def _campaign_insights(
        self,
        campaign_id: str,
        date_preset: str,
        time_range: dict | None,
        fields: list[str],
        breakdowns: list[str],
    ) -> dict:
        """Fetch insights for a specific campaign.

        Args:
            campaign_id: Meta campaign ID.
            date_preset: Meta ``date_preset`` string (e.g. ``"last_30d"``).
            time_range: Explicit ``{"since": "...", "until": "..."}`` date range.
            fields: List of insight field names to return.  Defaults to
                ``_DEFAULT_INSIGHT_FIELDS`` when empty.
            breakdowns: List of breakdown dimensions (e.g.
                ``["age", "gender"]``).

        Returns:
            A dict with an ``"insights"`` list.
        """
        import json as _json  # noqa: PLC0415

        selected_fields = fields if fields else _DEFAULT_INSIGHT_FIELDS
        params: dict[str, Any] = {"fields": ",".join(selected_fields)}
        params.update(self._build_date_params(date_preset, time_range))
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)

        data = self._get(f"/{campaign_id}/insights", params=params)
        insights = self._paginate(data)
        return {"insights": insights, "count": len(insights)}

    def _adset_insights(
        self,
        adset_id: str,
        time_range: dict | None,
    ) -> dict:
        """Fetch insights for an ad set.

        Args:
            adset_id: Meta ad set ID.
            time_range: Optional ``{"since": "...", "until": "..."}`` date range.

        Returns:
            A dict with an ``"insights"`` list.
        """
        params: dict[str, Any] = {"fields": ",".join(_DEFAULT_AD_FIELDS)}
        params.update(self._build_date_params("", time_range))
        data = self._get(f"/{adset_id}/insights", params=params)
        insights = self._paginate(data)
        return {"insights": insights, "count": len(insights)}

    def _ad_insights(
        self,
        ad_id: str,
        time_range: dict | None,
    ) -> dict:
        """Fetch insights for a single ad.

        Args:
            ad_id: Meta ad ID.
            time_range: Optional ``{"since": "...", "until": "..."}`` date range.

        Returns:
            A dict with an ``"insights"`` list.
        """
        params: dict[str, Any] = {"fields": ",".join(_DEFAULT_AD_FIELDS)}
        params.update(self._build_date_params("", time_range))
        data = self._get(f"/{ad_id}/insights", params=params)
        insights = self._paginate(data)
        return {"insights": insights, "count": len(insights)}

    def _account_insights(
        self,
        account_id: str,
        time_range: dict | None,
        breakdowns: list[str],
    ) -> dict:
        """Fetch account-level aggregate insights.

        Args:
            account_id: Meta ad account ID (e.g. ``"act_123456789"``).
            time_range: Optional ``{"since": "...", "until": "..."}`` date range.
            breakdowns: Optional breakdown dimensions.

        Returns:
            A dict with an ``"insights"`` list.
        """
        aid = self._normalise_account_id(account_id)
        params: dict[str, Any] = {"fields": ",".join(_DEFAULT_INSIGHT_FIELDS)}
        params.update(self._build_date_params("", time_range))
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)

        data = self._get(f"/{aid}/insights", params=params)
        insights = self._paginate(data)
        return {"insights": insights, "count": len(insights)}

    def _list_creatives(self, account_id: str) -> dict:
        """List ad creatives for an ad account.

        Args:
            account_id: Meta ad account ID.

        Returns:
            A dict with a ``"creatives"`` list.
        """
        aid = self._normalise_account_id(account_id)
        data = self._get(
            f"/{aid}/adcreatives",
            params={
                "fields": "id,name,status,body,title,image_url,"
                          "object_type,effective_object_story_id"
            },
        )
        creatives = self._paginate(data)
        return {"creatives": creatives, "count": len(creatives)}

    def _audience_estimate(
        self, account_id: str, targeting_spec: dict
    ) -> dict:
        """Estimate the potential reach for a targeting spec.

        Args:
            account_id: Meta ad account ID.
            targeting_spec: A Meta targeting spec dict (see Graph API docs for
                ``/reachestimate``).

        Returns:
            A dict with ``"users"`` (estimated reach), ``"estimate_ready"``,
            and ``"bid_estimations"`` where available.
        """
        import json as _json  # noqa: PLC0415

        if not targeting_spec:
            return {"error": "targeting_spec is required for audience_estimate."}

        aid = self._normalise_account_id(account_id)
        data = self._get(
            f"/{aid}/reachestimate",
            params={
                "targeting_spec": _json.dumps(targeting_spec),
                "optimize_for": "REACH",
            },
        )
        return data

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _normalise_account_id(self, account_id: str) -> str:
        """Ensure the account ID has the ``act_`` prefix.

        Args:
            account_id: Raw account ID (e.g. ``"123456789"`` or
                ``"act_123456789"``).

        Returns:
            An account ID string with the ``act_`` prefix.
        """
        aid = account_id.strip()
        if aid and not aid.startswith("act_"):
            aid = f"act_{aid}"
        return aid

    # ------------------------------------------------------------------
    # execute — operation dispatcher
    # ------------------------------------------------------------------

    def execute(  # noqa: PLR0913
        self,
        operation: str,
        account_id: str = "",
        campaign_id: str = "",
        adset_id: str = "",
        ad_id: str = "",
        status: str = "",
        date_preset: str = "",
        time_range: dict | None = None,
        fields: list | None = None,
        breakdowns: list | None = None,
        targeting_spec: dict | None = None,
    ) -> dict:
        """Dispatch to the requested Meta Ads operation.

        Args:
            operation: One of the supported operation names (see module docstring).
            account_id: Meta ad account ID (e.g. ``"act_123456789"`` or
                ``"123456789"``).  Required for account-level operations.
            campaign_id: Meta campaign ID.  Required for ``campaign_insights``.
            adset_id: Meta ad-set ID.  Required for ``adset_insights``.
            ad_id: Meta ad ID.  Required for ``ad_insights``.
            status: Effective status filter for ``list_campaigns``.  One of
                ``"ACTIVE"``, ``"PAUSED"``, ``"ARCHIVED"``, or empty for all.
            date_preset: Meta ``date_preset`` string (e.g. ``"last_30d"``,
                ``"last_7d"``, ``"this_month"``).  Used by insight operations.
            time_range: Explicit date range dict ``{"since": "YYYY-MM-DD",
                "until": "YYYY-MM-DD"}``.  Takes precedence over ``date_preset``
                when both are supplied.
            fields: List of insight field names to retrieve.  Uses a sensible
                default set when omitted.
            breakdowns: List of breakdown dimensions for insight operations
                (e.g. ``["age", "gender"]``, ``["publisher_platform"]``).
            targeting_spec: Meta targeting spec dict.  Required for
                ``audience_estimate``.

        Returns:
            Operation-specific dict on success, or ``{"error": "..."}`` on failure.
        """
        op = operation.strip().lower()

        try:
            if op == "list_accounts":
                return self._list_accounts()

            if op == "list_campaigns":
                return self._list_campaigns(account_id, status)

            if op == "campaign_insights":
                if not campaign_id.strip():
                    return {"error": "campaign_id is required for campaign_insights."}
                return self._campaign_insights(
                    campaign_id, date_preset, time_range, fields or [], breakdowns or []
                )

            if op == "adset_insights":
                if not adset_id.strip():
                    return {"error": "adset_id is required for adset_insights."}
                return self._adset_insights(adset_id, time_range)

            if op == "ad_insights":
                if not ad_id.strip():
                    return {"error": "ad_id is required for ad_insights."}
                return self._ad_insights(ad_id, time_range)

            if op == "account_insights":
                if not account_id.strip():
                    return {"error": "account_id is required for account_insights."}
                return self._account_insights(account_id, time_range, breakdowns or [])

            if op == "list_creatives":
                if not account_id.strip():
                    return {"error": "account_id is required for list_creatives."}
                return self._list_creatives(account_id)

            if op == "audience_estimate":
                if not account_id.strip():
                    return {"error": "account_id is required for audience_estimate."}
                return self._audience_estimate(account_id, targeting_spec or {})

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
