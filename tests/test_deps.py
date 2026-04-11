"""Tests for API dependency functions."""

import pytest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.deps import _resolve_token, extract_token


class TestResolveToken:
    def test_extracts_bearer_token(self):
        token = _resolve_token("Bearer ghp_abc123")
        assert token == "ghp_abc123"

    def test_falls_back_to_env(self):
        with patch("app.api.deps.settings") as mock_settings:
            mock_settings.github_token = "ghp_env_token"
            token = _resolve_token(None)
            assert token == "ghp_env_token"

    def test_falls_back_to_env_when_bearer_empty(self):
        with patch("app.api.deps.settings") as mock_settings:
            mock_settings.github_token = "ghp_env_token"
            token = _resolve_token("Bearer ")
            assert token == "ghp_env_token"

    def test_raises_when_no_token(self):
        with patch("app.api.deps.settings") as mock_settings:
            mock_settings.github_token = None
            with pytest.raises(HTTPException) as exc_info:
                _resolve_token(None)
            assert exc_info.value.status_code == 401

    def test_raises_when_no_bearer_prefix(self):
        with patch("app.api.deps.settings") as mock_settings:
            mock_settings.github_token = None
            with pytest.raises(HTTPException) as exc_info:
                _resolve_token("Basic dXNlcjpwYXNz")
            assert exc_info.value.status_code == 401

    def test_extract_token_function(self):
        token = extract_token("Bearer ghp_test")
        assert token == "ghp_test"


class TestResolveTokenEdgeCases:
    def test_bearer_with_extra_spaces(self):
        """'Bearer  two-spaces' extracts ' two-spaces' (leading space included)."""
        token = _resolve_token("Bearer  two-spaces")
        assert token == " two-spaces"

    def test_header_starts_with_bearer_no_space(self):
        """'BearerXYZ' should not match."""
        with patch("app.api.deps.settings") as mock_settings:
            mock_settings.github_token = None
            with pytest.raises(HTTPException):
                _resolve_token("BearerXYZ")
