"""Google Slides plugin for tbd-agents.

Uses a Google service-account JSON key (same auth pattern as
``google_sheets`` and ``bigquery_read``) so that LLM agents — typically a
Marketing Analyst building a deck of insights — can create new presentations
and append slides with text + images without going through OAuth.

Operations
----------
Read:
  - ``get_presentation`` – return basic metadata + slide IDs of a presentation.
  - ``list_slides``      – return ``[{slideId, index}]`` for every slide.

Write:
  - ``create_presentation`` – create a new, empty presentation and return its ID.
  - ``add_slide``           – append a blank slide with an optional title + body.
  - ``replace_text``        – global find-and-replace inside a presentation
    (useful for filling templated decks).

Authentication
--------------
Set ``GOOGLE_SLIDES_CREDENTIALS_JSON`` to the JSON string of a Google
service-account key. The service account needs **Editor** access to any
presentation it will modify (share the deck or use a Workspace domain-wide
delegation).
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.plugin_base import PluginBase

_SCOPES = ["https://www.googleapis.com/auth/presentations"]


class GoogleSlidesPlugin(PluginBase):
    """Google Slides plugin (read + write) for analyst / report agents."""

    @property
    def name(self) -> str:
        return "google_slides"

    @property
    def description(self) -> str:
        return (
            "Read and author Google Slides decks. "
            "Read: get_presentation, list_slides. "
            "Write: create_presentation, add_slide (with optional title/body), "
            "replace_text (find-and-replace). "
            "Authenticates via a Google service-account JSON key with Editor access."
        )

    @property
    def tags(self) -> list[str]:
        return [
            "google",
            "google_slides",
            "slides",
            "workspace",
            "reporting",
            "marketing",
            "read",
            "write",
        ]

    @property
    def env_config(self) -> dict[str, str]:
        return {"GOOGLE_SLIDES_CREDENTIALS_JSON": "{{token:google-slides-credentials}}"}

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        from google.oauth2 import service_account  # type: ignore
        from googleapiclient.discovery import build  # type: ignore

        creds_json = os.environ.get("GOOGLE_SLIDES_CREDENTIALS_JSON")
        if not creds_json:
            raise RuntimeError(
                "GOOGLE_SLIDES_CREDENTIALS_JSON environment variable is not set"
            )
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
        return build("slides", "v1", credentials=creds, cache_discovery=False)

    # ------------------------------------------------------------------
    # Operation dispatch
    # ------------------------------------------------------------------

    def execute(
        self,
        operation: str,
        presentation_id: str | None = None,
        title: str | None = None,
        body: str | None = None,
        find: str | None = None,
        replace: str | None = None,
        approval_token: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch on ``operation``. See class docstring for the full list."""
        op = (operation or "").strip().lower()
        write_ops = {"create_presentation", "add_slide", "replace_text"}
        if op in write_ops and not approval_token:
            return {
                "error": (
                    f"approval_token required for write operation '{op}'. "
                    "Pass approval_token=<id> after operator approval."
                )
            }
        try:
            client = self._get_client()
        except Exception as exc:  # pragma: no cover - import / auth failures
            return {"error": f"google_slides client error: {exc}"}

        try:
            if op == "get_presentation":
                if not presentation_id:
                    return {"error": "presentation_id is required"}
                pres = client.presentations().get(presentationId=presentation_id).execute()
                return {
                    "presentationId": pres.get("presentationId"),
                    "title": pres.get("title"),
                    "slideCount": len(pres.get("slides", [])),
                    "locale": pres.get("locale"),
                }
            if op == "list_slides":
                if not presentation_id:
                    return {"error": "presentation_id is required"}
                pres = client.presentations().get(presentationId=presentation_id).execute()
                return {
                    "slides": [
                        {"slideId": s.get("objectId"), "index": i}
                        for i, s in enumerate(pres.get("slides", []))
                    ]
                }
            if op == "create_presentation":
                if not title:
                    return {"error": "title is required for create_presentation"}
                pres = client.presentations().create(body={"title": title}).execute()
                return {
                    "presentationId": pres.get("presentationId"),
                    "title": pres.get("title"),
                }
            if op == "add_slide":
                if not presentation_id:
                    return {"error": "presentation_id is required"}
                requests: list[dict[str, Any]] = [
                    {
                        "createSlide": {
                            "slideLayoutReference": {"predefinedLayout": "TITLE_AND_BODY"},
                        }
                    }
                ]
                if title or body:
                    # Use placeholder text replacement on the freshly-created slide.
                    # First create the slide, then look it up to get placeholder IDs.
                    resp = client.presentations().batchUpdate(
                        presentationId=presentation_id,
                        body={"requests": requests},
                    ).execute()
                    new_slide_id = (
                        resp.get("replies", [{}])[0]
                        .get("createSlide", {})
                        .get("objectId")
                    )
                    pres = client.presentations().get(presentationId=presentation_id).execute()
                    placeholder_ids: dict[str, str] = {}
                    for slide in pres.get("slides", []):
                        if slide.get("objectId") != new_slide_id:
                            continue
                        for element in slide.get("pageElements", []):
                            ph = element.get("shape", {}).get("placeholder", {})
                            ph_type = ph.get("type")
                            if ph_type in {"TITLE", "BODY"}:
                                placeholder_ids[ph_type] = element.get("objectId")
                    fill_requests: list[dict[str, Any]] = []
                    if title and "TITLE" in placeholder_ids:
                        fill_requests.append(
                            {
                                "insertText": {
                                    "objectId": placeholder_ids["TITLE"],
                                    "text": title,
                                }
                            }
                        )
                    if body and "BODY" in placeholder_ids:
                        fill_requests.append(
                            {
                                "insertText": {
                                    "objectId": placeholder_ids["BODY"],
                                    "text": body,
                                }
                            }
                        )
                    if fill_requests:
                        client.presentations().batchUpdate(
                            presentationId=presentation_id,
                            body={"requests": fill_requests},
                        ).execute()
                    return {"slideId": new_slide_id, "title": title, "hasBody": bool(body)}
                resp = client.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={"requests": requests},
                ).execute()
                new_slide_id = (
                    resp.get("replies", [{}])[0]
                    .get("createSlide", {})
                    .get("objectId")
                )
                return {"slideId": new_slide_id}
            if op == "replace_text":
                if not presentation_id or find is None or replace is None:
                    return {"error": "presentation_id, find and replace are all required"}
                client.presentations().batchUpdate(
                    presentationId=presentation_id,
                    body={
                        "requests": [
                            {
                                "replaceAllText": {
                                    "containsText": {"text": find, "matchCase": False},
                                    "replaceText": replace,
                                }
                            }
                        ]
                    },
                ).execute()
                return {"find": find, "replace": replace, "status": "ok"}
            return {
                "error": (
                    f"Unknown operation '{operation}'. "
                    "Valid: get_presentation, list_slides, create_presentation, "
                    "add_slide, replace_text."
                )
            }
        except Exception as exc:  # pragma: no cover - network/api failures
            return {"error": f"google_slides API error: {exc}"}
