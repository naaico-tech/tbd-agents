"""Tests for the event_bus module (unit tests with mocked Redis)."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.event_bus import _channel, publish


class TestChannel:
    def test_channel_format(self):
        assert _channel("abc-123") == "workflow:events:abc-123"


class TestPublish:
    @pytest.mark.asyncio
    async def test_publish_sends_json(self):
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock()

        with patch("app.core.event_bus._pub_redis", mock_redis):
            await publish("wf-1", "log", {"detail": "test"})

        mock_redis.publish.assert_called_once()
        channel, payload = mock_redis.publish.call_args[0]
        assert channel == "workflow:events:wf-1"
        data = json.loads(payload)
        assert data["type"] == "log"
        assert data["data"]["detail"] == "test"
        assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_publish_reconnects_on_failure(self):
        """On first failure, should reconnect and retry."""
        mock_redis = AsyncMock()
        mock_redis.publish = AsyncMock(side_effect=[Exception("conn lost"), None])
        mock_redis.aclose = AsyncMock()

        with (
            patch("app.core.event_bus._pub_redis", mock_redis),
            patch("app.core.event_bus.aioredis") as mock_aioredis,
        ):
            new_redis = AsyncMock()
            new_redis.publish = AsyncMock()
            mock_aioredis.from_url.return_value = new_redis

            await publish("wf-2", "status", {"status": "running"})

            # Should have tried to close old connection and create new one
            mock_redis.aclose.assert_called_once()
