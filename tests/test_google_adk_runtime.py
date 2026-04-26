from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from google.genai import types

from app.models.provider import Provider, ProviderType
from app.services.google_adk_runtime import (
    GoogleAdkTool,
    build_google_adk_agent_name,
    build_google_adk_client_config,
    build_google_adk_model,
    build_google_adk_runtime_config,
    build_google_adk_session_service,
    dump_google_adk_session_service,
    extract_google_adk_text,
    google_adk_usage_to_dict,
    list_google_adk_models,
    normalize_google_adk_tool_result,
    resolve_google_adk_session_id,
    sanitize_google_adk_schema,
    validate_google_adk_provider_config,
)


class TestGoogleAdkRuntimeConfig:
    def test_build_client_config_for_gemini_api(self):
        provider = Provider.model_construct(
            name="google-adk",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-key",
            google_use_vertex_ai=False,
            google_cloud_project=None,
            google_cloud_location=None,
            base_url=None,
        )

        config = build_google_adk_client_config(provider, "gemini-secret")

        assert config == {
            "api_key": "gemini-secret",
            "use_vertex_ai": False,
            "project": None,
            "location": None,
            "base_url": None,
        }

    def test_build_runtime_config_for_gemini_api(self):
        provider = Provider.model_construct(
            name="google-adk",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-key",
            google_use_vertex_ai=False,
            google_cloud_project=None,
            google_cloud_location=None,
            base_url=None,
        )

        config = build_google_adk_runtime_config(
            provider,
            "gemini-secret",
            "gemini-2.5-flash",
        )

        assert config == {
            "model": "gemini-2.5-flash",
            "api_key": "gemini-secret",
            "use_vertex_ai": False,
            "project": None,
            "location": None,
            "base_url": None,
        }

    def test_build_runtime_config_for_vertex_ai_requires_project_and_location(self):
        provider = Provider.model_construct(
            name="google-adk-vertex",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-key",
            google_use_vertex_ai=True,
            google_cloud_project="",
            google_cloud_location=None,
            base_url=None,
        )

        with pytest.raises(ValueError, match="missing required field\\(s\\)"):
            build_google_adk_runtime_config(
                provider,
                "gemini-secret",
                "gemini-2.5-pro",
            )

    def test_build_runtime_config_for_vertex_ai_allows_missing_api_key(self):
        provider = Provider.model_construct(
            name="google-adk-vertex",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-key",
            google_use_vertex_ai=True,
            google_cloud_project="my-project",
            google_cloud_location="us-central1",
            base_url=None,
        )

        config = build_google_adk_runtime_config(
            provider,
            None,
            "gemini-2.5-pro",
        )

        assert config == {
            "model": "gemini-2.5-pro",
            "api_key": None,
            "use_vertex_ai": True,
            "project": "my-project",
            "location": "us-central1",
            "base_url": None,
        }

    def test_validate_google_adk_provider_config_requires_vertex_fields(self):
        provider = Provider.model_construct(
            name="google-adk-vertex",
            provider_type=ProviderType.GOOGLE_ADK,
            api_key_token_name="gemini-key",
            google_use_vertex_ai=True,
            google_cloud_project="",
            google_cloud_location=None,
        )

        with pytest.raises(ValueError, match="missing required field\\(s\\)"):
            validate_google_adk_provider_config(provider)

    def test_build_google_adk_model_preserves_explicit_config(self):
        model = build_google_adk_model(
            {
                "model": "gemini-2.5-flash",
                "api_key": "gemini-secret",
                "use_vertex_ai": True,
                "project": "my-project",
                "location": "us-central1",
                "base_url": "https://example.invalid",
            }
        )

        assert model.model == "gemini-2.5-flash"
        assert model.api_key == "gemini-secret"
        assert model.use_vertex_ai is True
        assert model.project == "my-project"
        assert model.location == "us-central1"
        assert model.base_url == "https://example.invalid"


class TestGoogleAdkToolHelpers:
    def test_build_google_adk_agent_name_sanitizes_hyphenated_prefix_and_object_id(self):
        name = build_google_adk_agent_name("69dcd725dee08e7a5f417d11")

        assert name == "tbd_agent_69dcd725dee08e7a5f417d11"
        assert name.isidentifier()

    def test_build_google_adk_agent_name_keeps_traceable_segments(self):
        name = build_google_adk_agent_name("workflow-alpha.69dcd725dee08e7a5f417d11")

        assert name == "tbd_agent_workflow_alpha_69dcd725dee08e7a5f417d11"
        assert name.isidentifier()

    def test_extract_google_adk_text_joins_visible_parts(self):
        response = SimpleNamespace(
            candidates=[
                SimpleNamespace(
                    content=SimpleNamespace(
                        parts=[
                            SimpleNamespace(text="Hello", thought=False),
                            SimpleNamespace(text=" hidden", thought=True),
                            SimpleNamespace(text=" world", thought=False),
                        ]
                    )
                )
            ]
        )

        assert extract_google_adk_text(response) == "Hello world"

    def test_google_adk_usage_to_dict_maps_usage_fields(self):
        usage = google_adk_usage_to_dict(
            SimpleNamespace(
                prompt_token_count=10,
                tool_use_prompt_token_count=5,
                candidates_token_count=7,
                cached_content_token_count=2,
            )
        )

        assert usage == {
            "prompt_tokens": 15,
            "completion_tokens": 7,
            "total_tokens": 22,
            "cached_tokens": 2,
        }

    def test_normalize_google_adk_tool_result_parses_json_strings(self):
        assert normalize_google_adk_tool_result('{"status":"ok"}') == {"status": "ok"}
        assert normalize_google_adk_tool_result("[1,2]") == {"result": [1, 2]}

    def test_sanitize_google_adk_schema_drops_unsupported_keys(self):
        schema = sanitize_google_adk_schema(
            {
                "type": "object",
                "title": "Ignored",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to inspect",
                        "default": ".",
                    }
                },
                "required": ["path"],
            }
        )

        assert "title" not in schema
        assert "default" not in schema["properties"]["path"]
        assert schema["properties"]["path"]["description"] == "Path to inspect"

    @pytest.mark.asyncio
    async def test_google_adk_tool_wraps_plain_text_results(self):
        executor = AsyncMock(return_value="hello")
        tool = GoogleAdkTool(
            name="echo",
            description="Echo input",
            schema={"type": "object", "properties": {}},
            executor=executor,
        )

        result = await tool.run_async(args={"message": "hello"}, tool_context=None)

        executor.assert_awaited_once_with({"message": "hello"})
        assert result == {"result": "hello"}

    @pytest.mark.asyncio
    async def test_list_google_adk_models_filters_to_generate_content(self):
        class _FakePager:
            def __init__(self, items):
                self._items = items

            def __aiter__(self):
                async def _iterate():
                    for item in self._items:
                        yield item

                return _iterate()

        fake_client = SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(
                    list=AsyncMock(
                        return_value=_FakePager(
                            [
                                types.Model(
                                    name="models/gemini-2.5-flash",
                                    display_name="Gemini 2.5 Flash",
                                    supported_actions=["generateContent"],
                                    input_token_limit=123,
                                    output_token_limit=456,
                                ),
                                types.Model(
                                    name="models/embedding-001",
                                    display_name="Embedding 001",
                                    supported_actions=["embedContent"],
                                ),
                            ]
                        )
                    )
                ),
                aclose=AsyncMock(),
            ),
            close=MagicMock(),
        )

        with patch(
            "app.services.google_adk_runtime.build_google_adk_client",
            return_value=fake_client,
        ):
            models = await list_google_adk_models(
                {
                    "api_key": "gemini-secret",
                    "use_vertex_ai": False,
                    "project": None,
                    "location": None,
                    "base_url": None,
                }
            )

        assert models == [
            {
                "id": "gemini-2.5-flash",
                "name": "Gemini 2.5 Flash",
                "provider_type": ProviderType.GOOGLE_ADK,
                "description": None,
                "input_token_limit": 123,
                "output_token_limit": 456,
                "supported_actions": ["generateContent"],
            }
        ]

    @pytest.mark.asyncio
    async def test_google_adk_session_service_restores_persisted_session(self):
        from google.adk.events import Event

        app_name = "tbd-agents-google-adk"
        user_id = "testuser"
        session_id = "workflow-123"

        session_service, restored = await build_google_adk_session_service(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        assert restored is False

        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        await session_service.append_event(
            session,
            Event(
                author="agent",
                content=types.Content(parts=[types.Part.from_text(text="hello")]),
            ),
        )

        snapshot = dump_google_adk_session_service(
            session_service,
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

        restored_service, restored = await build_google_adk_session_service(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            persisted_session=snapshot,
        )

        assert restored is True
        restored_session = await restored_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        assert [event.content.parts[0].text for event in restored_session.events] == ["hello"]

    def test_resolve_google_adk_session_id_prefers_persisted_snapshot(self):
        session_id = resolve_google_adk_session_id(
            app_name="tbd-agents-google-adk",
            user_id="testuser",
            fallback_session_id="workflow-session",
            persisted_session={
                "session": {
                    "app_name": "tbd-agents-google-adk",
                    "user_id": "testuser",
                    "id": "persisted-session",
                }
            },
        )

        assert session_id == "persisted-session"

    def test_resolve_google_adk_session_id_ignores_mismatched_snapshot(self):
        session_id = resolve_google_adk_session_id(
            app_name="tbd-agents-google-adk",
            user_id="testuser",
            fallback_session_id="workflow-session",
            persisted_session={
                "session": {
                    "app_name": "other-app",
                    "user_id": "testuser",
                    "id": "persisted-session",
                }
            },
        )

        assert session_id == "workflow-session"
