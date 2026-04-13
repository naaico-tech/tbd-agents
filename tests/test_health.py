"""Tests for the health check endpoint."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    with (
        patch("app.main.init_db", new_callable=AsyncMock),
        patch("app.main.init_telemetry"),
        patch("app.main.Instrumentator") as mock_instr,
    ):
        mock_inst = MagicMock()
        mock_inst.instrument.return_value = mock_inst
        mock_inst.expose = MagicMock()
        mock_instr.return_value = mock_inst

        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_response_format(self, client):
        resp = client.get("/health")
        data = resp.json()
        assert "status" in data
        assert isinstance(data["status"], str)
