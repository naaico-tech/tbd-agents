"""Tests for the event_bus module (unit tests with mocked Redis)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.event_bus import (
    _TASK_STATUS_STREAM,
    _channel,
    _history_key,
    get_events_since,
    publish,
)


class TestChannel:
    def test_channel_format(self):
        assert _channel("abc-123") == "workflow:events:abc-123"

    def test_history_key_format(self):
        assert _history_key("abc-123") == "workflow:history:abc-123"


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_sends_json_with_id(self):
        mock_pipe = AsyncMock()
        mock_pipe.publish = MagicMock()
        mock_pipe.rpush = MagicMock()
        mock_pipe.ltrim = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, 1, True, True])
        mock_pipe.xadd = MagicMock()

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("app.core.event_bus._pub_redis", mock_redis):
            await publish("wf-1", "log", {"detail": "test"})

        mock_redis.incr.assert_called_once()
        mock_pipe.publish.assert_called_once()
        channel = mock_pipe.publish.call_args[0][0]
        payload = mock_pipe.publish.call_args[0][1]
        assert channel == "workflow:events:wf-1"
        data = json.loads(payload)
        assert data["type"] == "log"
        assert data["data"]["detail"] == "test"
        assert data["id"] == 1
        assert "timestamp" in data
        # Stored in history
        mock_pipe.rpush.assert_called_once()
        mock_pipe.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_status_enqueues_task_status_event(self):
        mock_pipe = AsyncMock()
        mock_pipe.publish = MagicMock()
        mock_pipe.rpush = MagicMock()
        mock_pipe.ltrim = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, 1, True, "1-0", True])
        mock_pipe.xadd = MagicMock()

        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(return_value=7)
        mock_redis.expire = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipe)

        with patch("app.core.event_bus._pub_redis", mock_redis):
            await publish(
                "wf-1",
                "status",
                {
                    "status": "completed",
                    "current_turn": 2,
                    "task_execution_id": "task-123",
                },
            )

        mock_pipe.xadd.assert_called_once()
        stream_name, fields = mock_pipe.xadd.call_args[0]
        assert stream_name == _TASK_STATUS_STREAM
        assert fields["workflow_id"] == "wf-1"
        payload = json.loads(fields["payload"])
        assert payload["type"] == "status"
        assert payload["data"]["status"] == "completed"
        assert payload["data"]["task_execution_id"] == "task-123"
        assert payload["id"] == 7
        assert mock_pipe.expire.call_args_list[-1].args == (_TASK_STATUS_STREAM, 3600)

    @pytest.mark.asyncio
    async def test_publish_reconnects_on_failure(self):
        """On first failure, should reconnect and retry."""
        mock_redis = AsyncMock()
        mock_redis.incr = AsyncMock(side_effect=Exception("conn lost"))
        mock_redis.aclose = AsyncMock()

        mock_pipe = AsyncMock()
        mock_pipe.publish = MagicMock()
        mock_pipe.rpush = MagicMock()
        mock_pipe.ltrim = MagicMock()
        mock_pipe.expire = MagicMock()
        mock_pipe.execute = AsyncMock(return_value=[1, 1, True, True])
        mock_pipe.xadd = MagicMock()

        new_redis = AsyncMock()
        new_redis.incr = AsyncMock(return_value=1)
        new_redis.expire = AsyncMock()
        new_redis.pipeline = MagicMock(return_value=mock_pipe)

        with (
            patch("app.core.event_bus._pub_redis", mock_redis),
            patch("app.core.event_bus.aioredis") as mock_aioredis,
        ):
            mock_aioredis.from_url.return_value = new_redis

            await publish("wf-2", "status", {"status": "running"})

            # Should have tried to close old connection and create new one
            mock_redis.aclose.assert_called_once()


class TestGetEventsSince:
    @pytest.mark.asyncio
    async def test_returns_events_after_given_id(self):
        events = [
            json.dumps({"id": 1, "type": "log", "data": {}}),
            json.dumps({"id": 2, "type": "log", "data": {}}),
            json.dumps({"id": 3, "type": "status", "data": {}}),
        ]
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=events)
        mock_redis.aclose = AsyncMock()

        with patch("app.core.event_bus.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            result = await get_events_since("wf-1", 1)

        assert len(result) == 2
        assert json.loads(result[0])["id"] == 2
        assert json.loads(result[1])["id"] == 3

    @pytest.mark.asyncio
    async def test_returns_all_when_last_id_zero(self):
        events = [
            json.dumps({"id": 1, "type": "log", "data": {}}),
            json.dumps({"id": 2, "type": "log", "data": {}}),
        ]
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=events)
        mock_redis.aclose = AsyncMock()

        with patch("app.core.event_bus.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            result = await get_events_since("wf-1", 0)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_history(self):
        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[])
        mock_redis.aclose = AsyncMock()

        with patch("app.core.event_bus.aioredis") as mock_aioredis:
            mock_aioredis.from_url.return_value = mock_redis
            result = await get_events_since("wf-1", 5)

        assert result == []
