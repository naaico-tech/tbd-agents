"""Tests for app.config module."""

import os
from unittest.mock import patch

from app.config import Settings


class TestSettings:
    def test_default_values(self):
        """Settings should have sensible defaults."""
        s = Settings(
            _env_file=None,  # Don't read .env during tests
        )
        assert s.mongo_db_name == "copilot_agent_hub"
        assert s.default_model == "gpt-4.1"
        assert s.default_max_turns == 5
        assert s.session_timeout == 600
        assert s.github_token is None
        assert s.notion_token is None
        assert s.slack_bot_token is None
        assert s.token_encryption_key is None
        assert s.otel_service_name == "copilot-agent-hub"

    def test_env_override(self):
        """Settings should pick up environment variables."""
        with patch.dict(os.environ, {
            "MONGO_DB_NAME": "custom_db",
            "DEFAULT_MODEL": "gpt-3.5",
            "DEFAULT_MAX_TURNS": "10",
        }):
            s = Settings(_env_file=None)
            assert s.mongo_db_name == "custom_db"
            assert s.default_model == "gpt-3.5"
            assert s.default_max_turns == 10

    def test_extra_fields_ignored(self):
        """Extra env vars should not cause errors (extra='ignore')."""
        with patch.dict(os.environ, {"UNKNOWN_FIELD": "whatever"}):
            s = Settings(_env_file=None)
            assert not hasattr(s, "unknown_field")
