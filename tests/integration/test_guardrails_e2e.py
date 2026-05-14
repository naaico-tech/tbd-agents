"""Integration tests: guardrail enforcement end-to-end.

Verifies that guardrails stored in MongoDB are loaded and enforce
prompt validation (forbidden/required patterns, length) and request
schema validation through the API layer.

Closes #39
"""

import httpx
import pytest

from app.core.guardrails import enforce_guardrails
from app.models.guardrail import GuardrailType

from .conftest import create_agent, create_guardrail, create_workflow


class TestGuardrailEnforcement:
    # ------------------------------------------------------------------ #
    # Direct enforce_guardrails() tests (real DB, no HTTP)
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_forbidden_pattern_blocks_prompt(self):
        """A forbidden regex pattern causes a 422."""
        gr = await create_guardrail(
            name="no-secrets",
            guardrail_type=GuardrailType.PROMPT,
            forbidden_patterns=[r"sk-[A-Za-z0-9]+"],
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "My key is sk-abc123XYZ", None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_required_pattern_enforced(self):
        """A required pattern that is missing causes a 422."""
        gr = await create_guardrail(
            name="must-greet",
            guardrail_type=GuardrailType.PROMPT,
            required_patterns=[r"^(hello|hi)"],
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "Do something bad", None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_required_pattern_passes(self):
        """Prompt matching all required patterns is accepted."""
        gr = await create_guardrail(
            name="must-greet",
            guardrail_type=GuardrailType.PROMPT,
            required_patterns=[r"^hello"],
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        result = await enforce_guardrails(wf, "hello world", None)
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_min_length_enforced(self):
        """Prompt shorter than min_length is rejected."""
        gr = await create_guardrail(
            name="min-len",
            guardrail_type=GuardrailType.PROMPT,
            min_length=20,
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "short", None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_max_length_enforced(self):
        """Prompt exceeding max_length is rejected."""
        gr = await create_guardrail(
            name="max-len",
            guardrail_type=GuardrailType.PROMPT,
            max_length=10,
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "This prompt is way too long for the limit", None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_request_json_schema_validation(self):
        """Request data validated against JSON schema."""
        gr = await create_guardrail(
            name="schema-check",
            guardrail_type=GuardrailType.REQUEST,
            json_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        # Valid request
        result = await enforce_guardrails(wf, None, {"name": "Alice"})
        assert "Alice" in result

        # Invalid request — missing required field
        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, None, {"age": 30})

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_tag_based_guardrail_loading(self):
        """Guardrails are loaded by tag match, not just by explicit ID."""
        gr = await create_guardrail(
            name="tagged-guard",
            guardrail_type=GuardrailType.PROMPT,
            tags=["safety"],
            forbidden_patterns=[r"DROP TABLE"],
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_tags=["safety"])

        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "DROP TABLE users", None)

        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_disabled_guardrail_ignored(self):
        """Disabled guardrails are not enforced."""
        gr = await create_guardrail(
            name="disabled-guard",
            guardrail_type=GuardrailType.PROMPT,
            forbidden_patterns=[r"forbidden"],
            enabled=False,
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        # Should pass because guardrail is disabled
        result = await enforce_guardrails(wf, "This has forbidden word", None)
        assert result == "This has forbidden word"

    # ------------------------------------------------------------------ #
    # API-level guardrail tests (via TestClient)
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_prompt_endpoint_enforces_guardrails(
        self, app_client: httpx.AsyncClient, auth_headers: dict,
    ):
        """POST /prompt rejects prompts blocked by guardrails."""
        gr = await create_guardrail(
            name="api-guard",
            guardrail_type=GuardrailType.PROMPT,
            forbidden_patterns=[r"hack"],
        )
        agent = await create_agent()
        wf = await create_workflow(agent, guardrail_ids=[str(gr.id)])

        resp = await app_client.post(
            f"/api/workflows/{wf.id}/prompt",
            json={"prompt": "hack the system"},
            headers=auth_headers,
        )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_multiple_guardrails_all_enforced(self):
        """All attached guardrails are checked, not just the first."""
        gr1 = await create_guardrail(
            name="no-sql-inject",
            guardrail_type=GuardrailType.PROMPT,
            forbidden_patterns=[r"SELECT.*FROM"],
        )
        gr2 = await create_guardrail(
            name="no-scripts",
            guardrail_type=GuardrailType.PROMPT,
            forbidden_patterns=[r"<script>"],
        )
        agent = await create_agent()
        wf = await create_workflow(
            agent, guardrail_ids=[str(gr1.id), str(gr2.id)],
        )

        # First guardrail blocks
        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "SELECT name FROM users", None)
        assert exc_info.value.status_code == 422

        # Second guardrail blocks
        with pytest.raises(Exception) as exc_info:
            await enforce_guardrails(wf, "inject <script>alert(1)</script>", None)
        assert exc_info.value.status_code == 422

        # Clean prompt passes both
        result = await enforce_guardrails(wf, "Hello, how are you?", None)
        assert result == "Hello, how are you?"
