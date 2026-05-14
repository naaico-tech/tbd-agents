from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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
        patch("app.api.routes.models.build_client", return_value=_FakeClient()) as mock_build_client,
    ):
        data = await list_models(
            _user={"login": "local"},
            authorization=None,
            provider_id="6601a1b2c3d4e5f607890abc",
        )

    assert data == [{"id": "gpt-4.1", "name": "GPT-4.1"}]
    mock_build_client.assert_called_once_with("ghp_stored_token")
