"""Tests for legacy dashboard routes."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    import app.main as app_main

    with (
        patch.object(app_main, "init_db", new_callable=AsyncMock),
        patch.object(app_main, "init_telemetry"),
        patch.object(app_main, "Instrumentator") as mock_instr,
        patch.object(app_main.plugin_loader, "load_plugins_from_config", new_callable=AsyncMock),
    ):
        mock_inst = MagicMock()
        mock_inst.instrument.return_value = mock_inst
        mock_inst.expose = MagicMock()
        mock_instr.return_value = mock_inst

        with TestClient(app_main.app, raise_server_exceptions=False) as test_client:
            yield test_client


class TestLegacyDashboardRoutes:
    @staticmethod
    def _create_flutter_build(tmp_path):
        flutter_dir = tmp_path / "flutter-web"
        assets_dir = flutter_dir / "assets"
        assets_dir.mkdir(parents=True)
        (flutter_dir / "index.html").write_text(
            "<html><body><h1>FLUTTER DASHBOARD</h1></body></html>",
            encoding="utf-8",
        )
        (assets_dir / "app.js").write_text("console.log('flutter');", encoding="utf-8")
        return flutter_dir

    def test_dashboard_route_serves_flutter_dashboard_when_available(self, client, tmp_path):
        import app.main as app_main

        flutter_dir = self._create_flutter_build(tmp_path)

        with patch.object(app_main, "FLUTTER_STATIC_DIR", flutter_dir):
            resp = client.get("/dashboard")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "FLUTTER DASHBOARD" in resp.text

    def test_dashboard_nested_route_falls_back_to_flutter_index(self, client, tmp_path):
        import app.main as app_main

        flutter_dir = self._create_flutter_build(tmp_path)

        with patch.object(app_main, "FLUTTER_STATIC_DIR", flutter_dir):
            resp = client.get("/dashboard/agents")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "FLUTTER DASHBOARD" in resp.text

    def test_dashboard_asset_route_serves_built_asset(self, client, tmp_path):
        import app.main as app_main

        flutter_dir = self._create_flutter_build(tmp_path)

        with patch.object(app_main, "FLUTTER_STATIC_DIR", flutter_dir):
            resp = client.get("/dashboard/assets/app.js")

        assert resp.status_code == 200
        assert "console.log('flutter');" in resp.text

    def test_dashboard_asset_route_blocks_hidden_files(self, client, tmp_path):
        import app.main as app_main

        flutter_dir = self._create_flutter_build(tmp_path)
        (flutter_dir / ".env").write_text("SECRET=true", encoding="utf-8")

        with patch.object(app_main, "FLUTTER_STATIC_DIR", flutter_dir):
            resp = client.get("/dashboard/.env")

        assert resp.status_code == 404

    def test_dashboard_legacy_route_serves_legacy_ui(self, client):
        resp = client.get("/dashboard-legacy?embed=1&page=agents")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert 'data-page="agents"' in resp.text

    def test_dashboard_route_falls_back_to_legacy_when_flutter_missing(self, client):
        import app.main as app_main

        with patch.object(app_main, "FLUTTER_STATIC_DIR", None):
            resp = client.get("/dashboard")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "TBD AGENT" in resp.text

    def test_dashboard_legacy_alias_route_serves_same_dashboard(self, client):
        resp = client.get("/dashboard-legacy?embed=1&page=agents")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert 'data-page="agents"' in resp.text
