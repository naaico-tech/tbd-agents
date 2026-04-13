"""Tests for the copilot_client module."""

from unittest.mock import MagicMock, patch

from app.services.copilot_client import build_client


class TestBuildClient:
    @patch("app.services.copilot_client.CopilotClient")
    @patch("app.services.copilot_client.SubprocessConfig")
    @patch("app.services.copilot_client.settings")
    def test_creates_client(self, mock_settings, MockConfig, MockCopilotClient):
        mock_settings.otel_http_endpoint = ""
        MockConfig.return_value = MagicMock()
        MockCopilotClient.return_value = MagicMock()

        client = build_client("ghp_test_token")

        MockConfig.assert_called_once()
        call_kwargs = MockConfig.call_args
        assert call_kwargs.kwargs["github_token"] == "ghp_test_token"
        assert call_kwargs.kwargs["use_stdio"] is True

    @patch("app.services.copilot_client.CopilotClient")
    @patch("app.services.copilot_client.SubprocessConfig")
    @patch("app.services.copilot_client.settings")
    def test_includes_telemetry_when_configured(self, mock_settings, MockConfig, MockCopilotClient):
        mock_settings.otel_http_endpoint = "http://collector:4318"
        MockConfig.return_value = MagicMock()
        MockCopilotClient.return_value = MagicMock()

        client = build_client("ghp_test_token")

        call_kwargs = MockConfig.call_args
        assert call_kwargs.kwargs["telemetry"] is not None
        assert call_kwargs.kwargs["telemetry"]["otlp_endpoint"] == "http://collector:4318"

    @patch("app.services.copilot_client.CopilotClient")
    @patch("app.services.copilot_client.SubprocessConfig")
    @patch("app.services.copilot_client.settings")
    def test_no_telemetry_when_empty(self, mock_settings, MockConfig, MockCopilotClient):
        mock_settings.otel_http_endpoint = ""
        MockConfig.return_value = MagicMock()
        MockCopilotClient.return_value = MagicMock()

        client = build_client("ghp_test_token")

        call_kwargs = MockConfig.call_args
        assert call_kwargs.kwargs["telemetry"] is None
