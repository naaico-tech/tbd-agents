from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.models import list_models
from app.models.provider import ProviderType


class _FakeClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def list_models(self):
        return [SimpleNamespace(to_dict=lambda: {"id": "gpt-4.1", "name": "GPT-4.1"})]


@pytest.mark.asyncio
async def test_list_models_uses_github_copilot_provider_token_when_selected():
    provider = SimpleNamespace(
        id="6601a1b2c3d4e5f607890abc",
        name="copilot-byok",
        provider_type=ProviderType.GITHUB_COPILOT,
        api_key_token_name="copilot-token",
    )

    with (
        patch("app.api.routes.models.Provider.get", new=AsyncMock(return_value=provider)),
        patch(
            "app.api.routes.models.token_manager.get_token_value",
            new=AsyncMock(return_value="ghp_stored_token"),
        ),
        patch(
            "app.api.routes.models.build_client", return_value=_FakeClient()
        ) as mock_build_client,
    ):
        data = await list_models(
            _user={"login": "local"},
            authorization=None,
            provider_id="6601a1b2c3d4e5f607890abc",
        )

    assert data == [{"id": "gpt-4.1", "name": "GPT-4.1"}]
    mock_build_client.assert_called_once_with("ghp_stored_token")


@pytest.mark.asyncio
async def test_list_models_uses_google_adk_provider_when_selected():
    provider = SimpleNamespace(
        id="6601a1b2c3d4e5f607890abd",
        name="google-adk",
        provider_type=ProviderType.GOOGLE_ADK,
        api_key_token_name="gemini-token",
        google_use_vertex_ai=False,
        google_cloud_project=None,
        google_cloud_location=None,
        base_url=None,
    )

    expected_models = [
        {
            "id": "gemini-2.5-flash",
            "name": "Gemini 2.5 Flash",
            "provider_type": ProviderType.GOOGLE_ADK,
            "description": "Fast Gemini",
            "input_token_limit": 1048576,
            "output_token_limit": 8192,
            "supported_actions": ["generateContent"],
        }
    ]

    with (
        patch("app.api.routes.models.Provider.get", new=AsyncMock(return_value=provider)),
        patch(
            "app.api.routes.models.token_manager.get_token_value",
            new=AsyncMock(return_value="gemini-secret"),
        ),
        patch(
            "app.api.routes.models.list_google_adk_models",
            new=AsyncMock(return_value=expected_models),
        ) as mock_list_models,
    ):
        data = await list_models(
            _user={"login": "local"},
            authorization=None,
            provider_id="6601a1b2c3d4e5f607890abd",
        )

    assert data == expected_models
    mock_list_models.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_models_rejects_google_adk_provider_without_stored_token():
    provider = SimpleNamespace(
        id="6601a1b2c3d4e5f607890abe",
        name="google-adk",
        provider_type=ProviderType.GOOGLE_ADK,
        api_key_token_name="missing-gemini-token",
    )

    with (
        patch("app.api.routes.models.Provider.get", new=AsyncMock(return_value=provider)),
        patch(
            "app.api.routes.models.token_manager.get_token_value",
            new=AsyncMock(return_value=None),
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await list_models(
                _user={"login": "local"},
                authorization=None,
                provider_id="6601a1b2c3d4e5f607890abe",
            )

    assert exc_info.value.status_code == 400
    assert "requires a stored Gemini API key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_list_models_allows_keyless_google_adk_vertex_provider():
    provider = SimpleNamespace(
        id="6601a1b2c3d4e5f607890abf",
        name="google-adk-vertex",
        provider_type=ProviderType.GOOGLE_ADK,
        api_key_token_name="missing-gemini-token",
        google_use_vertex_ai=True,
        google_cloud_project="my-project",
        google_cloud_location="us-central1",
        base_url=None,
    )
    expected_models = [{"id": "gemini-2.5-pro", "name": "Gemini 2.5 Pro"}]

    with (
        patch("app.api.routes.models.Provider.get", new=AsyncMock(return_value=provider)),
        patch(
            "app.api.routes.models.token_manager.get_token_value",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.api.routes.models.list_google_adk_models",
            new=AsyncMock(return_value=expected_models),
        ) as mock_list_models,
    ):
        data = await list_models(
            _user={"login": "local"},
            authorization=None,
            provider_id="6601a1b2c3d4e5f607890abf",
        )

    assert data == expected_models
    runtime_config = mock_list_models.await_args.args[0]
    assert runtime_config["api_key"] is None
    assert runtime_config["use_vertex_ai"] is True


@pytest.mark.asyncio
async def test_list_models_rejects_misconfigured_keyless_google_adk_vertex_provider():
    provider = SimpleNamespace(
        id="6601a1b2c3d4e5f607890ac0",
        name="google-adk-vertex",
        provider_type=ProviderType.GOOGLE_ADK,
        api_key_token_name="missing-gemini-token",
        google_use_vertex_ai=True,
        google_cloud_project="",
        google_cloud_location=None,
        base_url=None,
    )

    with (
        patch("app.api.routes.models.Provider.get", new=AsyncMock(return_value=provider)),
        patch(
            "app.api.routes.models.token_manager.get_token_value",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "app.api.routes.models.list_google_adk_models",
            new=AsyncMock(),
        ) as mock_list_models,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await list_models(
                _user={"login": "local"},
                authorization=None,
                provider_id="6601a1b2c3d4e5f607890ac0",
            )

    assert exc_info.value.status_code == 400
    assert "missing required field(s)" in exc_info.value.detail
    mock_list_models.assert_not_awaited()
