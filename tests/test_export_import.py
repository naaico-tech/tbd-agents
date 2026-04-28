"""Tests for the import/export API endpoints.

Auth note: FastAPI's Depends() captures the get_current_user function object at
import time, so patch() on the module attribute has no effect.  The correct way
to override a FastAPI dependency in tests is app.dependency_overrides.  The
autouse fixture 'override_auth' sets a "testuser" override for every test in
this module and tears it down afterwards.
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user
from app.main import app as _app

# ── Constants ─────────────────────────────────────────────────────────────────

FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_ID_2 = "6601a1b2c3d4e5f607890abd"
AUTH_USER = {"login": "testuser", "id": 1, "name": "Test User"}

# ── Auth override fixture ─────────────────────────────────────────────────────


def _make_user_override(login: str = "testuser"):
    """Return a dependency override callable that yields the given user dict."""

    def _dep():
        return {"login": login, "id": 1, "name": "Test User"}

    return _dep


@pytest.fixture(autouse=True)
def override_auth():
    """Override get_current_user for every test in this module."""
    _app.dependency_overrides[get_current_user] = _make_user_override("testuser")
    yield
    _app.dependency_overrides.pop(get_current_user, None)


# ── Fake model helpers ────────────────────────────────────────────────────────


def _fake_skill():
    return SimpleNamespace(
        id=FAKE_ID,
        name="Test Skill",
        description="A skill",
        instructions="Do something",
        tags=["tag1"],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _fake_agent():
    return SimpleNamespace(
        id=FAKE_ID,
        name="Test Agent",
        description="An agent",
        system_prompt="You are a test assistant.",
        model="gpt-4.1",
        mcp_server_ids=[],
        mcp_server_tags=[],
        tool_definitions=[],
        knowledge_source_ids=[],
        knowledge_tags=[],
        builtin_tools=[],
        custom_tool_ids=[],
        provider_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _fake_workflow(github_user: str = "testuser"):
    return SimpleNamespace(
        id=FAKE_ID,
        title="Test Workflow",
        agent_id=FAKE_ID,
        github_user=github_user,
        model="gpt-4.1",
        max_turns=5,
        current_turn=0,
        session_id=None,
        skill_ids=[],
        skill_tags=[],
        output_format="json",
        infinite_session=True,
        caveman=False,
        bypass_memory=False,
        auto_memory=False,
        tsv_tool_results=False,
        reasoning_effort=None,
        guardrail_ids=[],
        guardrail_tags=[],
        repo_url=None,
        repo_branch=None,
        repo_token_name=None,
        usage=None,
        logs=[],
        messages=[],
        status="active",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _fake_knowledge_source():
    return SimpleNamespace(
        id=FAKE_ID,
        name="Test KS",
        description="A knowledge source",
        source_type="vector_db",
        connection_config={"url": "http://qdrant:6333", "collection": "docs"},
        tags=["docs"],
        status="registered",
        last_error=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ── Skills export ────────────────────────────────────────────────────────────


class TestSkillsExport:
    def test_export_all_skills(self, app_client):
        skill = _fake_skill()
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[skill])

        with patch(
            "app.api.routes.skills.Skill.find_all",
            return_value=mock_find,
        ):
            resp = app_client.get("/api/skills/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "skill"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test Skill"
        assert data["items"][0]["instructions"] == "Do something"

    def test_export_all_skills_empty(self, app_client):
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[])

        with patch(
            "app.api.routes.skills.Skill.find_all",
            return_value=mock_find,
        ):
            resp = app_client.get("/api/skills/export")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    def test_export_single_skill(self, app_client):
        skill = _fake_skill()
        with patch(
            "app.api.routes.skills.Skill.get",
            new_callable=AsyncMock,
            return_value=skill,
        ):
            resp = app_client.get(f"/api/skills/{FAKE_ID}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["tags"] == ["tag1"]

    def test_export_single_skill_not_found(self, app_client):
        with patch(
            "app.api.routes.skills.Skill.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.get(f"/api/skills/{FAKE_ID}/export")
        assert resp.status_code == 404

    def test_import_skills(self, app_client):
        inserted_skill = MagicMock()
        inserted_skill.id = FAKE_ID
        inserted_skill.insert = AsyncMock()

        with patch("app.api.routes.skills.Skill", return_value=inserted_skill):
            resp = app_client.post(
                "/api/skills/import",
                json={
                    "items": [
                        {
                            "name": "New Skill",
                            "description": "desc",
                            "instructions": "do it",
                            "tags": ["a"],
                        }
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1
        assert data["errors"] == []
        assert len(data["ids"]) == 1

    def test_import_skills_handles_error(self, app_client):
        with patch(
            "app.api.routes.skills.Skill",
            side_effect=ValueError("bad data"),
        ):
            resp = app_client.post(
                "/api/skills/import",
                json={"items": [{"name": "Bad", "instructions": "x"}]},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert len(data["errors"]) == 1
        assert "Bad" in data["errors"][0]


# ── Agents export ────────────────────────────────────────────────────────────


class TestAgentsExport:
    def test_export_all_agents(self, app_client):
        agent = _fake_agent()
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[agent])

        with patch(
            "app.api.routes.agents.Agent.find_all",
            return_value=mock_find,
        ):
            resp = app_client.get("/api/agents/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "agent"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test Agent"

    def test_export_single_agent(self, app_client):
        agent = _fake_agent()
        with patch(
            "app.api.routes.agents.Agent.get",
            new_callable=AsyncMock,
            return_value=agent,
        ):
            resp = app_client.get(f"/api/agents/{FAKE_ID}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["system_prompt"] == "You are a test assistant."

    def test_export_single_agent_not_found(self, app_client):
        with patch(
            "app.api.routes.agents.Agent.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.get(f"/api/agents/{FAKE_ID}/export")
        assert resp.status_code == 404

    def test_import_agents(self, app_client):
        inserted_agent = MagicMock()
        inserted_agent.id = FAKE_ID
        inserted_agent.insert = AsyncMock()

        with patch("app.api.routes.agents.Agent", return_value=inserted_agent):
            resp = app_client.post(
                "/api/agents/import",
                json={
                    "items": [
                        {
                            "name": "Imported Agent",
                            "description": "imported",
                            "system_prompt": "You are helpful.",
                        }
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1
        assert data["errors"] == []

    def test_import_agents_handles_error(self, app_client):
        with patch(
            "app.api.routes.agents.Agent",
            side_effect=RuntimeError("db error"),
        ):
            resp = app_client.post(
                "/api/agents/import",
                json={"items": [{"name": "ErrAgent", "system_prompt": "x"}]},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert "ErrAgent" in data["errors"][0]


# ── Workflows export ─────────────────────────────────────────────────────────


class TestWorkflowsExport:
    def test_export_all_workflows(self, app_client):
        wf = _fake_workflow("testuser")
        # Patch the whole Workflow class so Workflow.github_user (a Beanie
        # ExpressionField) is available as a MagicMock and the filter
        # expression Workflow.github_user == user["login"] doesn't raise
        # AttributeError when Beanie is not initialised.
        with patch("app.api.routes.workflows.Workflow") as mock_workflow:
            mock_workflow.find.return_value.to_list = AsyncMock(return_value=[wf])
            resp = app_client.get("/api/workflows/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "workflow"
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Test Workflow"

    def test_export_single_workflow(self, app_client):
        wf = _fake_workflow("testuser")
        with patch(
            "app.api.routes.workflows.Workflow.get",
            new_callable=AsyncMock,
            return_value=wf,
        ):
            resp = app_client.get(f"/api/workflows/{FAKE_ID}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["model"] == "gpt-4.1"

    def test_export_single_workflow_not_found(self, app_client):
        with patch(
            "app.api.routes.workflows.Workflow.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.get(f"/api/workflows/{FAKE_ID}/export")
        assert resp.status_code == 404

    def test_export_single_workflow_wrong_user(self, app_client):
        """Exporting another user's workflow returns 403."""
        wf = _fake_workflow("other_user")
        with patch(
            "app.api.routes.workflows.Workflow.get",
            new_callable=AsyncMock,
            return_value=wf,
        ):
            resp = app_client.get(f"/api/workflows/{FAKE_ID}/export")
        assert resp.status_code == 403
        assert "Not your workflow" in resp.json()["detail"]

    def test_import_workflows(self, app_client):
        agent = _fake_agent()
        inserted_wf = MagicMock()
        inserted_wf.id = FAKE_ID_2
        inserted_wf.insert = AsyncMock()

        with (
            patch(
                "app.api.routes.workflows.Agent.get",
                new_callable=AsyncMock,
                return_value=agent,
            ),
            patch(
                "app.api.routes.workflows.Workflow",
                return_value=inserted_wf,
            ),
        ):
            resp = app_client.post(
                "/api/workflows/import",
                json={
                    "items": [
                        {
                            "title": "Imported WF",
                            "agent_id": FAKE_ID,
                            "model": "gpt-4.1",
                            "max_turns": 5,
                        }
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1
        assert data["errors"] == []

    def test_import_workflows_missing_agent(self, app_client):
        """Import with a non-existent agent_id records an error."""
        with patch(
            "app.api.routes.workflows.Agent.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.post(
                "/api/workflows/import",
                json={
                    "items": [
                        {
                            "title": "Missing Agent WF",
                            "agent_id": FAKE_ID,
                            "model": "gpt-4.1",
                        }
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert len(data["errors"]) == 1
        assert "agent_id" in data["errors"][0]


# ── Knowledge sources export ─────────────────────────────────────────────────


class TestKnowledgeSourcesExport:
    def test_export_all_knowledge_sources(self, app_client):
        ks = _fake_knowledge_source()
        mock_find = MagicMock()
        mock_find.to_list = AsyncMock(return_value=[ks])

        with patch(
            "app.api.routes.knowledge_sources.KnowledgeSource.find_all",
            return_value=mock_find,
        ):
            resp = app_client.get("/api/knowledge-sources/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "knowledge_source"
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test KS"

    def test_export_single_knowledge_source(self, app_client):
        ks = _fake_knowledge_source()
        with patch(
            "app.api.routes.knowledge_sources.KnowledgeSource.get",
            new_callable=AsyncMock,
            return_value=ks,
        ):
            resp = app_client.get(f"/api/knowledge-sources/{FAKE_ID}/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["source_type"] == "vector_db"

    def test_export_single_knowledge_source_not_found(self, app_client):
        with patch(
            "app.api.routes.knowledge_sources.KnowledgeSource.get",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = app_client.get(f"/api/knowledge-sources/{FAKE_ID}/export")
        assert resp.status_code == 404

    def test_import_knowledge_sources(self, app_client):
        inserted_ks = MagicMock()
        inserted_ks.id = FAKE_ID
        inserted_ks.insert = AsyncMock()

        with patch(
            "app.api.routes.knowledge_sources.KnowledgeSource",
            return_value=inserted_ks,
        ):
            resp = app_client.post(
                "/api/knowledge-sources/import",
                json={
                    "items": [
                        {
                            "name": "Imported KS",
                            "source_type": "vector_db",
                            "connection_config": {},
                            "tags": [],
                        }
                    ]
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 1
        assert data["errors"] == []

    def test_import_knowledge_sources_handles_error(self, app_client):
        with patch(
            "app.api.routes.knowledge_sources.KnowledgeSource",
            side_effect=ValueError("invalid type"),
        ):
            resp = app_client.post(
                "/api/knowledge-sources/import",
                json={"items": [{"name": "Bad KS", "source_type": "bad_type"}]},
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created"] == 0
        assert "Bad KS" in data["errors"][0]


# ── Full bundle export/import ────────────────────────────────────────────────


class TestFullBundleExport:
    def test_export_all(self, app_client):
        skill = _fake_skill()
        agent = _fake_agent()
        wf = _fake_workflow("testuser")
        ks = _fake_knowledge_source()

        mock_skill_find = MagicMock()
        mock_skill_find.to_list = AsyncMock(return_value=[skill])
        mock_agent_find = MagicMock()
        mock_agent_find.to_list = AsyncMock(return_value=[agent])
        mock_ks_find = MagicMock()
        mock_ks_find.to_list = AsyncMock(return_value=[ks])

        with (
            patch(
                "app.api.routes.export_import.Skill.find_all",
                return_value=mock_skill_find,
            ),
            patch(
                "app.api.routes.export_import.Agent.find_all",
                return_value=mock_agent_find,
            ),
            # Patch whole Workflow class so Workflow.github_user exists as a
            # MagicMock and the filter expression doesn't raise AttributeError.
            patch("app.api.routes.export_import.Workflow") as mock_workflow,
            patch(
                "app.api.routes.export_import.KnowledgeSource.find_all",
                return_value=mock_ks_find,
            ),
        ):
            mock_workflow.find.return_value.to_list = AsyncMock(return_value=[wf])
            resp = app_client.get("/api/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resource_type"] == "bundle"
        assert len(data["skills"]) == 1
        assert len(data["agents"]) == 1
        assert len(data["workflows"]) == 1
        assert len(data["knowledge_sources"]) == 1

    def test_export_all_empty(self, app_client):
        mock_skill_find = MagicMock()
        mock_skill_find.to_list = AsyncMock(return_value=[])
        mock_agent_find = MagicMock()
        mock_agent_find.to_list = AsyncMock(return_value=[])
        mock_ks_find = MagicMock()
        mock_ks_find.to_list = AsyncMock(return_value=[])

        with (
            patch(
                "app.api.routes.export_import.Skill.find_all",
                return_value=mock_skill_find,
            ),
            patch(
                "app.api.routes.export_import.Agent.find_all",
                return_value=mock_agent_find,
            ),
            patch("app.api.routes.export_import.Workflow") as mock_workflow_cls,
            patch(
                "app.api.routes.export_import.KnowledgeSource.find_all",
                return_value=mock_ks_find,
            ),
        ):
            mock_workflow_cls.find.return_value.to_list = AsyncMock(return_value=[])
            resp = app_client.get("/api/export")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skills"] == []
        assert data["agents"] == []
        assert data["workflows"] == []
        assert data["knowledge_sources"] == []


class TestFullBundleImport:
    def test_import_all_bundle(self, app_client):
        inserted_skill = MagicMock()
        inserted_skill.id = FAKE_ID
        inserted_skill.insert = AsyncMock()

        inserted_agent = MagicMock()
        inserted_agent.id = FAKE_ID
        inserted_agent.insert = AsyncMock()

        inserted_wf = MagicMock()
        inserted_wf.id = FAKE_ID_2
        inserted_wf.insert = AsyncMock()

        inserted_ks = MagicMock()
        inserted_ks.id = FAKE_ID
        inserted_ks.insert = AsyncMock()

        fake_agent = _fake_agent()

        with (
            patch(
                "app.api.routes.export_import.Skill",
                return_value=inserted_skill,
            ),
            patch(
                "app.api.routes.export_import.Agent",
                return_value=inserted_agent,
            ),
            patch(
                "app.api.routes.export_import.Agent.get",
                new_callable=AsyncMock,
                return_value=fake_agent,
            ),
            patch(
                "app.api.routes.export_import.Workflow",
                return_value=inserted_wf,
            ),
            patch(
                "app.api.routes.export_import.KnowledgeSource",
                return_value=inserted_ks,
            ),
        ):
            resp = app_client.post(
                "/api/import",
                json={
                    "skills": [
                        {"name": "S1", "instructions": "do it", "tags": []}
                    ],
                    "agents": [{"name": "A1", "system_prompt": "Hi"}],
                    "workflows": [
                        {
                            "title": "WF1",
                            "agent_id": FAKE_ID,
                            "model": "gpt-4.1",
                        }
                    ],
                    "knowledge_sources": [
                        {
                            "name": "KS1",
                            "source_type": "mongo_db",
                            "connection_config": {},
                            "tags": [],
                        }
                    ],
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["skills"]["created"] == 1
        assert data["agents"]["created"] == 1
        assert data["workflows"]["created"] == 1
        assert data["knowledge_sources"]["created"] == 1

    def test_import_all_bundle_missing_agent(self, app_client):
        """Workflows with a missing agent_id are recorded as errors; rest proceed."""
        inserted_skill = MagicMock()
        inserted_skill.id = FAKE_ID
        inserted_skill.insert = AsyncMock()

        inserted_ks = MagicMock()
        inserted_ks.id = FAKE_ID
        inserted_ks.insert = AsyncMock()

        with (
            patch(
                "app.api.routes.export_import.Skill",
                return_value=inserted_skill,
            ),
            patch(
                "app.api.routes.export_import.Agent",
                return_value=MagicMock(id=FAKE_ID, insert=AsyncMock()),
            ),
            patch(
                "app.api.routes.export_import.Agent.get",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "app.api.routes.export_import.KnowledgeSource",
                return_value=inserted_ks,
            ),
        ):
            resp = app_client.post(
                "/api/import",
                json={
                    "skills": [{"name": "S1", "instructions": "do it"}],
                    "agents": [{"name": "A1", "system_prompt": "Hi"}],
                    "workflows": [
                        {
                            "title": "Missing Agent WF",
                            "agent_id": FAKE_ID,
                            "model": "gpt-4.1",
                        }
                    ],
                    "knowledge_sources": [
                        {
                            "name": "KS1",
                            "source_type": "mongo_db",
                            "connection_config": {},
                        }
                    ],
                },
            )
        assert resp.status_code == 201
        data = resp.json()
        assert data["workflows"]["created"] == 0
        assert len(data["workflows"]["errors"]) == 1
        assert "agent_id" in data["workflows"]["errors"][0]

    def test_import_empty_bundle(self, app_client):
        resp = app_client.post(
            "/api/import",
            json={
                "skills": [],
                "agents": [],
                "workflows": [],
                "knowledge_sources": [],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["skills"]["created"] == 0
        assert data["agents"]["created"] == 0
        assert data["workflows"]["created"] == 0
        assert data["knowledge_sources"]["created"] == 0


# ── Schema unit tests ────────────────────────────────────────────────────────


class TestExportImportSchemas:
    def test_exported_skill_defaults(self):
        from app.schemas.export_import import ExportedSkill

        s = ExportedSkill(name="Skill", instructions="Do it")
        assert s.description == ""
        assert s.tags == []

    def test_skill_export_bundle(self):
        from app.schemas.export_import import ExportedSkill, SkillExportBundle

        bundle = SkillExportBundle(
            items=[ExportedSkill(name="S", instructions="x")]
        )
        assert bundle.version == "1.0"
        assert bundle.resource_type == "skill"
        assert len(bundle.items) == 1

    def test_agent_export_bundle(self):
        from app.schemas.export_import import AgentExportBundle, ExportedAgent

        bundle = AgentExportBundle(items=[ExportedAgent(name="A")])
        assert bundle.resource_type == "agent"

    def test_workflow_export_bundle(self):
        from app.schemas.export_import import ExportedWorkflow, WorkflowExportBundle

        bundle = WorkflowExportBundle(
            items=[ExportedWorkflow(title="WF", agent_id=FAKE_ID, model="gpt-4.1")]
        )
        assert bundle.resource_type == "workflow"

    def test_knowledge_source_export_bundle(self):
        from app.schemas.export_import import (
            ExportedKnowledgeSource,
            KnowledgeSourceExportBundle,
        )

        bundle = KnowledgeSourceExportBundle(
            items=[
                ExportedKnowledgeSource(
                    name="KS", source_type="vector_db", connection_config={}
                )
            ]
        )
        assert bundle.resource_type == "knowledge_source"

    def test_full_export_bundle_defaults(self):
        from app.schemas.export_import import FullExportBundle

        bundle = FullExportBundle()
        assert bundle.resource_type == "bundle"
        assert bundle.skills == []
        assert bundle.agents == []
        assert bundle.workflows == []
        assert bundle.knowledge_sources == []

    def test_import_result(self):
        from app.schemas.export_import import ImportResult

        r = ImportResult(created=2, ids=["a", "b"], errors=["oops"])
        assert r.created == 2
        assert len(r.ids) == 2
        assert len(r.errors) == 1
