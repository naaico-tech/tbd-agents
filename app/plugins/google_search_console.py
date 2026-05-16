"""Google Search Console (read-only) plugin for tbd-agents.

Authenticates via a Google service-account JSON key (same pattern as
``bigquery_read`` and ``google_sheets``). The service account must be added
as a **user** to each Search Console property it should query — Search Console
does not support domain-wide delegation.

Operations
----------
- ``list_sites`` – list verified Search Console properties accessible to the
  service account.
- ``query``      – run a Search Analytics query against one property.
  Returns the top rows broken down by the given dimensions
  (``query``, ``page``, ``country``, ``device``, ``searchAppearance``, ``date``).
- ``inspect_url`` – run a URL Inspection (index status, mobile usability,
  canonical) for a single URL.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.plugin_base import PluginBase

_SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]

_VALID_DIMENSIONS = {"query", "page", "country", "device", "searchAppearance", "date"}
_MAX_ROWS_HARD_LIMIT = 25_000


class GoogleSearchConsolePlugin(PluginBase):
    """Read-only Google Search Console plugin for SEO / marketing agents."""

    @property
    def name(self) -> str:
        return "google_search_console"

    @property
    def description(self) -> str:
        return (
            "Read-only Google Search Console access. "
            "Operations: list_sites (list properties), query (Search Analytics by "
            "dimensions query/page/country/device/date), inspect_url (URL Inspection "
            "API for index status / canonical / mobile usability)."
        )

    @property
    def tags(self) -> list[str]:
        return [
            "google",
            "search_console",
            "gsc",
            "seo",
            "web-analytics",
            "marketing",
            "read",
        ]

    @property
    def env_config(self) -> dict[str, str]:
        return {
            "GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON": "{{token:google-search-console-credentials}}"
        }

    def _get_client(self):
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore

        creds_json = os.environ.get("GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON")
        if not creds_json:
            raise RuntimeError(
                "GOOGLE_SEARCH_CONSOLE_CREDENTIALS_JSON environment variable is not set"
            )
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
        return build("searchconsole", "v1", credentials=creds, cache_discovery=False)

    def execute(
        self,
        operation: str,
        site_url: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        dimensions: list[str] | None = None,
        row_limit: int = 1000,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch on ``operation``."""
        op = (operation or "").strip().lower()
        try:
            client = self._get_client()
        except Exception as exc:  # pragma: no cover
            return {"error": f"google_search_console client error: {exc}"}

        try:
            if op == "list_sites":
                resp = client.sites().list().execute()
                return {
                    "sites": [
                        {
                            "siteUrl": s.get("siteUrl"),
                            "permissionLevel": s.get("permissionLevel"),
                        }
                        for s in resp.get("siteEntry", [])
                    ]
                }
            if op == "query":
                if not site_url or not start_date or not end_date:
                    return {"error": "site_url, start_date, end_date are all required"}
                dims = dimensions or ["query"]
                bad = [d for d in dims if d not in _VALID_DIMENSIONS]
                if bad:
                    return {
                        "error": (
                            f"Invalid dimensions: {bad}. "
                            f"Valid: {sorted(_VALID_DIMENSIONS)}"
                        )
                    }
                if row_limit > _MAX_ROWS_HARD_LIMIT:
                    row_limit = _MAX_ROWS_HARD_LIMIT
                resp = client.searchanalytics().query(
                    siteUrl=site_url,
                    body={
                        "startDate": start_date,
                        "endDate": end_date,
                        "dimensions": dims,
                        "rowLimit": row_limit,
                    },
                ).execute()
                rows = resp.get("rows", [])
                return {
                    "rowCount": len(rows),
                    "dimensions": dims,
                    "rows": [
                        {
                            "keys": r.get("keys"),
                            "clicks": r.get("clicks"),
                            "impressions": r.get("impressions"),
                            "ctr": r.get("ctr"),
                            "position": r.get("position"),
                        }
                        for r in rows
                    ],
                }
            if op == "inspect_url":
                if not site_url or not url:
                    return {"error": "site_url and url are both required"}
                resp = client.urlInspection().index().inspect(
                    body={"inspectionUrl": url, "siteUrl": site_url}
                ).execute()
                inspection = resp.get("inspectionResult", {})
                idx = inspection.get("indexStatusResult", {})
                return {
                    "url": url,
                    "verdict": idx.get("verdict"),
                    "coverageState": idx.get("coverageState"),
                    "googleCanonical": idx.get("googleCanonical"),
                    "userCanonical": idx.get("userCanonical"),
                    "mobileUsability": inspection.get("mobileUsabilityResult", {}).get(
                        "verdict"
                    ),
                    "lastCrawlTime": idx.get("lastCrawlTime"),
                }
            return {
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Valid: list_sites, query, inspect_url."
                )
            }
        except Exception as exc:  # pragma: no cover
            return {"error": f"google_search_console API error: {exc}"}
