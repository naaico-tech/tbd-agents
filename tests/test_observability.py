"""Tests for observability metrics and instrumentation.

Covers:
- Prometheus metric definitions (celery_queue_length, sse_connections_active)
- SSE connection gauge tracking in the stream endpoint
- Celery queue length polling

Closes #60
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMetricDefinitions:
    """All expected custom Prometheus metrics exist as module-level singletons."""

    def test_celery_queue_length_gauge_exists(self):
        from app.observability import celery_queue_length

        assert celery_queue_length._name == "copilot_hub_celery_queue_length"

    def test_sse_connections_active_gauge_exists(self):
        from app.observability import sse_connections_active

        assert sse_connections_active._name == "copilot_hub_sse_connections_active"

    def test_all_expected_metrics_importable(self):
        from app.observability import (
            agent_task_duration_seconds,
            agent_tasks_active,
            agent_tasks_total,
            celery_queue_length,
            cost_dollars_total,
            cost_per_task_dollars,
            mcp_connections_total,
            premium_requests_total,
            repo_sync_duration_seconds,
            repo_sync_total,
            sse_connections_active,
            tokens_total,
            tool_calls_per_task,
            tool_calls_total,
        )

        # Verify all are non-None
        metrics = [
            agent_task_duration_seconds,
            agent_tasks_active,
            agent_tasks_total,
            celery_queue_length,
            cost_dollars_total,
            cost_per_task_dollars,
            mcp_connections_total,
            premium_requests_total,
            repo_sync_duration_seconds,
            repo_sync_total,
            sse_connections_active,
            tokens_total,
            tool_calls_per_task,
            tool_calls_total,
        ]
        assert all(m is not None for m in metrics)


class TestSSEConnectionGauge:
    """sse_connections_active is incremented/decremented around SSE streams."""

    @pytest.mark.asyncio
    async def test_sse_gauge_increments_and_decrements(self):
        """The SSE event_generator increments the gauge on entry and
        decrements on exit (via finally)."""
        from app.observability import sse_connections_active

        # Reset gauge for test isolation
        sse_connections_active._value.set(0.0)

        inc_calls = 0
        dec_calls = 0
        original_inc = sse_connections_active.inc
        original_dec = sse_connections_active.dec

        def track_inc(*a, **kw):
            nonlocal inc_calls
            inc_calls += 1
            return original_inc(*a, **kw)

        def track_dec(*a, **kw):
            nonlocal dec_calls
            dec_calls += 1
            return original_dec(*a, **kw)

        with (
            patch.object(sse_connections_active, "inc", side_effect=track_inc),
            patch.object(sse_connections_active, "dec", side_effect=track_dec),
        ):
            # Import stream endpoint after patching
            from app.api.routes.workflows import stream_workflow

            # Create mock request and workflow
            mock_request = MagicMock()
            mock_request.is_disconnected = AsyncMock(return_value=False)

            mock_wf = MagicMock()
            mock_wf.id = "aabbccddeeff00112233aabb"

            events = [
                json.dumps({"type": "status", "data": {"status": "done"}}),
            ]

            async def fake_subscribe(wf_id, last_event_id=None):
                for e in events:
                    yield e

            with (
                patch("app.api.routes.workflows.Workflow") as MockWf,
                patch(
                    "app.core.event_bus.subscribe",
                    side_effect=fake_subscribe,
                ),
            ):
                MockWf.get = AsyncMock(return_value=mock_wf)

                resp = await stream_workflow(
                    workflow_id="aabbccddeeff00112233aabb",
                    request=mock_request,
                    last_event_id=None,
                )

                # Consume the streaming response body
                body = b""
                async for chunk in resp.body_iterator:
                    body += chunk.encode() if isinstance(chunk, str) else chunk

        assert inc_calls == 1, "sse_connections_active.inc() should be called once"
        assert dec_calls == 1, "sse_connections_active.dec() should be called once"


class TestCeleryQueuePoller:
    """_poll_celery_queue reads Redis llen and updates celery_queue_length."""

    @pytest.mark.asyncio
    async def test_poll_reads_queue_length(self):
        from app.main import _poll_celery_queue
        from app.observability import celery_queue_length

        celery_queue_length._value.set(0.0)

        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(return_value=7)
        mock_redis.aclose = AsyncMock()

        stop = asyncio.Event()

        async def run_one_iteration():
            """Let the poller run one iteration then stop."""
            await asyncio.sleep(0.05)
            stop.set()

        with patch("app.main.aioredis.from_url", return_value=mock_redis):
            await asyncio.gather(
                _poll_celery_queue(stop),
                run_one_iteration(),
            )

        mock_redis.llen.assert_called_with("celery")
        assert celery_queue_length._value.get() == 7.0

    @pytest.mark.asyncio
    async def test_poll_handles_redis_errors_gracefully(self):
        from app.main import _poll_celery_queue
        from app.observability import celery_queue_length

        celery_queue_length._value.set(0.0)

        mock_redis = AsyncMock()
        mock_redis.llen = AsyncMock(side_effect=ConnectionError("gone"))
        mock_redis.aclose = AsyncMock()

        stop = asyncio.Event()

        async def stop_soon():
            await asyncio.sleep(0.05)
            stop.set()

        with patch("app.main.aioredis.from_url", return_value=mock_redis):
            await asyncio.gather(
                _poll_celery_queue(stop),
                stop_soon(),
            )

        # Should not raise; gauge stays at 0
        assert celery_queue_length._value.get() == 0.0
