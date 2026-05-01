"""Smoke checks for the legacy static admin UI (`app/static/index.html`).

These tests exist to guard against accidental regressions in the vanilla-JS
bits that wire the live indexing-progress UX onto the repositories page.
There's no JS runtime here — we just assert the expected symbols are present
in the file. Cheap regression net.
"""

from pathlib import Path

import pytest

INDEX_HTML = Path(__file__).resolve().parents[1] / "app" / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    assert INDEX_HTML.exists(), f"missing static UI: {INDEX_HTML}"
    return INDEX_HTML.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "needle",
    [
        # New JS surface for live job progress.
        "function attachJob(",
        "function detachJob(",
        "function renderJobProgress(",
        "function pollJobUntilTerminal(",
        "const activeJobs = new Map();",
        # SSE consumer.
        "new EventSource(",
        "EventSource.CLOSED",
        # New CSS hook.
        ".repo-job-strip",
        # Per-row progress slot rendered by loadRepositories().
        'id="repo-progress-${r.id}"',
        # Async-enqueue endpoints are still wired correctly.
        "/api/code-repositories/${id}/index",
        "/api/code-repositories/${id}/sync",
        "/jobs/${jobId}/events",
    ],
)
def test_static_ui_contains_progress_hooks(html: str, needle: str) -> None:
    assert needle in html, f"missing expected token in static UI: {needle!r}"


def test_legacy_handlers_no_longer_expect_old_response_shapes(html: str) -> None:
    # The pre-async toasts should be gone — we now toast "queued" / "attaching".
    assert "Sync ${res.status}" not in html
    assert "Indexed ${res.file_count} files / ${res.chunk_count} chunks" not in html
    assert "Index job queued" in html or "Sync job queued" in html


# ── Regression guards for SSE lifecycle bugs ────────────────────────────────


def test_done_handler_closes_event_source_before_map_delete(html: str) -> None:
    # The browser's auto-reconnect must be silenced before we forget the entry.
    snippet = html.split("es.addEventListener('done'", 1)[1].split("es.onerror", 1)[0]
    close_idx = snippet.find("es.close()")
    delete_idx = snippet.find("activeJobs.delete(repoId)")
    assert close_idx != -1 and delete_idx != -1
    assert close_idx < delete_idx, "es.close() must be called before activeJobs.delete()"


def test_done_handler_guards_against_empty_payload(html: str) -> None:
    # Backend sends `data: {}` on done; UI must fall back to lastSnapshot
    # instead of re-rendering the strip as state='queued'.
    assert "info.lastSnapshot || { id: jobId }" in html
    assert "info.gotDone = true" in html


def test_onerror_skips_polling_after_normal_done(html: str) -> None:
    # After a normal `done`, the trailing browser-fired error must not start polling.
    assert "if (info.gotDone)" in html


def test_dismiss_job_closes_event_source(html: str) -> None:
    # dismissJob → detachJob → es.close() + clearInterval.
    detach = html.split("function detachJob(", 1)[1].split("\n}", 1)[0]
    assert "info.es && info.es.close()" in detach
    assert "clearInterval(info.pollTimer)" in detach
    assert "activeJobs.delete(repoId)" in detach


def test_poll_loop_has_kill_switch(html: str) -> None:
    # pollJobUntilTerminal's tick() must bail if dismissed / replaced.
    poll = html.split("function pollJobUntilTerminal(", 1)[1].split("\n}\n", 1)[0]
    assert "activeJobs.get(repoId)" in poll
    assert "cur.jobId !== jobId" in poll


def test_route_leave_iterates_activejobs_snapshot(html: str) -> None:
    # Must iterate a snapshot, not the live Map (detachJob mutates it).
    assert "Array.from(activeJobs.keys())" in html


def test_poll_fallback_detaches_prior_tracker(html: str) -> None:
    # Avoid clobbering a fresher attach: detach existing entry first.
    poll = html.split("function pollJobUntilTerminal(", 1)[1].split("\n}\n", 1)[0]
    assert "detachJob(repoId)" in poll
