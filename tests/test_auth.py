"""Tests for the auth service (GitHub token validation)."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
from fastapi import HTTPException

from app.services.auth import validate_github_token


class TestValidateGitHubToken:
    @pytest.mark.asyncio
    async def test_valid_token(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "login": "testuser",
            "id": 42,
            "name": "Test User",
        }

        with patch("app.services.auth.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await validate_github_token("ghp_valid_token")
            assert result == {"login": "testuser", "id": 42, "name": "Test User"}

            mock_client.get.assert_called_once()
            call_kwargs = mock_client.get.call_args
            assert "Bearer ghp_valid_token" in str(call_kwargs)

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("app.services.auth.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await validate_github_token("ghp_bad_token")
            assert exc_info.value.status_code == 401
            assert "Invalid or expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_expired_token(self):
        mock_response = MagicMock()
        mock_response.status_code = 403

        with patch("app.services.auth.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            with pytest.raises(HTTPException) as exc_info:
                await validate_github_token("ghp_expired")
            assert exc_info.value.status_code == 401
