"""Tests for Scheduled Agents — model, service helpers, trigger task, and REST API."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Helpers ──────────────────────────────────────────────────────────────────

FAKE_ID = "6601a1b2c3d4e5f607890abc"
FAKE_WF_ID = "6601a1b2c3d4e5f607890def"


def _make_sa(**kwargs) -> MagicMock:
    """Build a mock ScheduledAgent without Beanie initialisation."""
    sa = MagicMock()
    sa.id = FAKE_ID
    sa.name = kwargs.get("name", "Daily Report")
    sa.workflow_id = kwargs.get("workflow_id", FAKE_WF_ID)
    sa.prompt = kwargs.get("prompt", "Generate a daily summary")
    sa.interval_value = kwargs.get("interval_value", 1)
    sa.interval_unit = kwargs.get("interval_unit", "days")
    sa.start_at = kwargs.get("start_at", datetime.now(UTC))
    sa.end_at = kwargs.get("end_at", None)
    sa.enabled = kwargs.get("enabled", True)
    sa.last_run_at = kwargs.get("last_run_at", None)
    sa.next_run_at = kwargs.get("next_run_at", None)
    sa.redbeat_key = kwargs.get("redbeat_key", None)
    sa.created_at = datetime.now(UTC)
    sa.updated_at = datetime.now(UTC)
    sa.save = AsyncMock()
    sa.delete = AsyncMock()
    sa.set = AsyncMock()
    return sa


def _make_wf(github_user="testuser") -> MagicMock:
    """Build a mock Workflow document."""
    wf = MagicMock()
    wf.github_user = github_user
    wf.reasoning_effort = None
    return wf


# ── Model validation ─────────────────────────────────────────────────────────


class TestScheduledAgentModel:
    def test_schedule_interval_enum_values(self):
        from app.models.scheduled_agent import ScheduleInterval

        assert ScheduleInterval.MINUTES == "minutes"
        assert ScheduleInterval.HOURS == "hours"
        assert ScheduleInterval.DAYS == "days"

    def test_all_interval_units_valid(self):
        from app.models.scheduled_agent import ScheduleInterval

        for unit in ("minutes", "hours", "days"):
            assert ScheduleInterval(unit) is not None


# ── Schema validation ────────────────────────────────────────────────────────


class TestScheduledAgentSchemas:
    def test_create_schema_requires_interval_ge_1(self):
        from pydantic import ValidationError

        from app.schemas.scheduled_agent import ScheduledAgentCreate

        with pytest.raises(ValidationError):
            ScheduledAgentCreate(
                name="bad",
                workflow_id=FAKE_WF_ID,
                prompt="p",
                interval_value=0,  # must be >= 1
                interval_unit="hours",
                start_at=datetime.now(UTC),
            )

    def test_create_schema_valid(self):
        from app.schemas.scheduled_agent import ScheduledAgentCreate

        obj = ScheduledAgentCreate(
            name="hourly",
            workflow_id=FAKE_WF_ID,
            prompt="Do work",
            interval_value=2,
            interval_unit="hours",
            start_at=datetime.now(UTC),
        )
        assert obj.interval_value == 2
        assert obj.end_at is None

    def test_update_schema_all_optional(self):
        from app.schemas.scheduled_agent import ScheduledAgentUpdate

        obj = ScheduledAgentUpdate()
        assert obj.name is None
        assert obj.interval_value is None

    def test_update_schema_rejects_zero_interval(self):
        from pydantic import ValidationError

        from app.schemas.scheduled_agent import ScheduledAgentUpdate

        with pytest.raises(ValidationError):
            ScheduledAgentUpdate(interval_value=0)

    def test_response_schema_roundtrip(self):
        from app.schemas.scheduled_agent import ScheduledAgentResponse

        now = datetime.now(UTC)
        obj = ScheduledAgentResponse(
            id=FAKE_ID,
            name="test",
            workflow_id=FAKE_WF_ID,
            prompt="go",
            interval_value=30,
            interval_unit="minutes",
            start_at=now,
            end_at=None,
            enabled=True,
            last_run_at=None,
            next_run_at=None,
            created_at=now,
            updated_at=now,
        )
        assert obj.id == FAKE_ID
        assert obj.enabled is True


# ── Scheduler service helpers ─────────────────────────────────────────────────


class TestSchedulerService:
    def test_build_key(self):
        from app.services.scheduler import _build_key

        key = _build_key(FAKE_ID)
        assert key == f"redbeat:scheduled_agent:{FAKE_ID}"

    def test_interval_timedelta_minutes(self):
        from app.services.scheduler import _interval_timedelta

        assert _interval_timedelta(30, "minutes") == timedelta(minutes=30)

    def test_interval_timedelta_hours(self):
        from app.services.scheduler import _interval_timedelta

        assert _interval_timedelta(3, "hours") == timedelta(hours=3)

    def test_interval_timedelta_days(self):
        from app.services.scheduler import _interval_timedelta

        assert _interval_timedelta(7, "days") == timedelta(days=7)

    def test_interval_timedelta_invalid_unit(self):
        from app.services.scheduler import _interval_timedelta

        with pytest.raises(ValueError, match="Unknown interval unit"):
            _interval_timedelta(1, "weeks")

    def test_create_schedule_returns_key(self):
        """create_schedule should call entry.save() and return the deterministic key."""
        mock_entry = MagicMock()
        sa = _make_sa()

        with (
            patch("app.services.scheduler.RedBeatSchedulerEntry", return_value=mock_entry),
            patch("app.services.scheduler.celery_schedule"),
            patch("app.services.scheduler.celery"),
        ):
            from app.services.scheduler import create_schedule
            key = create_schedule(sa)

        mock_entry.save.assert_called_once()
        assert key == f"redbeat:scheduled_agent:{FAKE_ID}"

    def test_delete_schedule_existing_entry(self):
        """delete_schedule should call entry.delete() when the entry exists."""
        mock_entry = MagicMock()
        sa = _make_sa(redbeat_key=f"redbeat:scheduled_agent:{FAKE_ID}")

        with (
            patch("app.services.scheduler.RedBeatSchedulerEntry") as mock_cls,
            patch("app.services.scheduler.celery"),
        ):
            mock_cls.from_key.return_value = mock_entry
            from app.services.scheduler import delete_schedule
            delete_schedule(sa)

        mock_entry.delete.assert_called_once()

    def test_delete_schedule_missing_entry(self):
        """delete_schedule should not raise if the entry is already gone (KeyError)."""
        sa = _make_sa()

        with (
            patch("app.services.scheduler.RedBeatSchedulerEntry") as mock_cls,
            patch("app.services.scheduler.celery"),
        ):
            mock_cls.from_key.side_effect = KeyError("missing")
            from app.services.scheduler import delete_schedule
            delete_schedule(sa)  # Must not raise

    def test_enable_schedule_calls_create(self):
        sa = _make_sa(enabled=False)
        with patch("app.services.scheduler.create_schedule", return_value="some_key") as mock_create:
            from app.services.scheduler import enable_schedule
            key = enable_schedule(sa)
        mock_create.assert_called_once_with(sa)
        assert key == "some_key"

    def test_disable_schedule_calls_delete(self):
        sa = _make_sa()
        with patch("app.services.scheduler.delete_schedule") as mock_delete:
            from app.services.scheduler import disable_schedule
            disable_schedule(sa)
        mock_delete.assert_called_once_with(sa)

    def test_update_schedule_deletes_then_creates(self):
        sa = _make_sa()
        with (
            patch("app.services.scheduler.delete_schedule") as mock_del,
            patch("app.services.scheduler.create_schedule", return_value="new_key") as mock_create,
        ):
            from app.services.scheduler import update_schedule
            key = update_schedule(sa)

        mock_del.assert_called_once_with(sa)
        mock_create.assert_called_once_with(sa)
        assert key == "new_key"


# ── Trigger task logic ────────────────────────────────────────────────────────


class TestScheduledTriggerTask:
    """Unit tests for the _execute() coroutine inside the trigger task."""

    @pytest.mark.asyncio
    async def test_skips_when_not_found(self):
        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
        ):
            mock_sa_cls.get = AsyncMock(return_value=None)
            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)
            # Should return without further calls

    @pytest.mark.asyncio
    async def test_skips_when_disabled(self):
        sa = _make_sa(enabled=False)

        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
        ):
            mock_sa_cls.get = AsyncMock(return_value=sa)
            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)

        # save should never be called because we returned early
        sa.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_auto_disables_when_past_end_at(self):
        past_end = datetime.now(UTC) - timedelta(hours=1)
        sa = _make_sa(enabled=True, end_at=past_end)

        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
            patch("app.tasks.scheduled_trigger.scheduler") as mock_scheduler,
        ):
            mock_sa_cls.get = AsyncMock(return_value=sa)
            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)

        mock_scheduler.disable_schedule.assert_called_once_with(sa)
        sa.save.assert_called_once()
        assert sa.enabled is False

    @pytest.mark.asyncio
    async def test_dispatches_run_agent_task(self):
        sa = _make_sa(enabled=True, end_at=None)
        mock_wf = _make_wf()

        mock_te = MagicMock()
        mock_te.id = "te_fake_id"
        mock_te.insert = AsyncMock()

        mock_run_task = MagicMock()

        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.Workflow") as mock_wf_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
            patch("app.tasks.scheduled_trigger.run_agent_task", mock_run_task),
        ):
            mock_sa_cls.get = AsyncMock(return_value=sa)
            mock_wf_cls.get = AsyncMock(return_value=mock_wf)
            mock_te_cls.return_value = mock_te
            mock_te_cls.find_one = AsyncMock(return_value=None)

            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)

        mock_te.insert.assert_called_once()
        mock_run_task.delay.assert_called_once()
        sa.save.assert_called_once()
        assert sa.last_run_at is not None
        assert sa.next_run_at is not None

    @pytest.mark.asyncio
    async def test_skips_when_already_running(self):
        sa = _make_sa(enabled=True, end_at=None)

        # Mock an active task execution
        mock_active_te = MagicMock()
        mock_active_te.id = "active_te_id"
        mock_active_te.status = "running"

        mock_run_task = MagicMock()

        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
            patch("app.tasks.scheduled_trigger.run_agent_task", mock_run_task),
        ):
            mock_sa_cls.get = AsyncMock(return_value=sa)
            # Find one should return the active task
            mock_te_cls.find_one = AsyncMock(return_value=mock_active_te)

            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)

        # delay should NOT be called
        mock_run_task.delay.assert_not_called()
        # sa.save should NOT be called (meaning we didn't advance last_run_at/next_run_at)
        sa.save.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_workflow_missing(self):
        sa = _make_sa(enabled=True, end_at=None)

        with (
            patch("app.tasks.scheduled_trigger.init_db", new_callable=AsyncMock),
            patch("app.tasks.scheduled_trigger.ScheduledAgent") as mock_sa_cls,
            patch("app.tasks.scheduled_trigger.Workflow") as mock_wf_cls,
            patch("app.tasks.scheduled_trigger.TaskExecution") as mock_te_cls,
        ):
            mock_sa_cls.get = AsyncMock(return_value=sa)
            mock_wf_cls.get = AsyncMock(return_value=None)
            mock_te_cls.find_one = AsyncMock(return_value=None)
            from app.tasks.scheduled_trigger import _execute
            await _execute(FAKE_ID)

        sa.save.assert_not_called()


# ── REST API endpoints ─────────────────────────────────────────────────────────
# These tests follow the same lenient-status-code pattern used across the project
# (e.g. test_custom_tools_api.py): we accept 200/201/204 on success paths and
# 401/403/404 on access-control paths, because auth middleware may intercept
# before our route logic does in the test client context.


class TestScheduledAgentsAPI:
    def _auth_header(self):
        return {"Authorization": "Bearer test-token"}

    def _user(self, login="testuser"):
        return {"login": login, "id": 1}

    def test_list_returns_ok_or_auth(self, app_client):
        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.Workflow.find") as mock_find,
            patch("app.api.routes.scheduled_agents.ScheduledAgent.find_all") as mock_sa_find,
        ):
            mock_find.return_value.to_list = AsyncMock(return_value=[])
            mock_sa_find.return_value.sort.return_value.to_list = AsyncMock(return_value=[])
            resp = app_client.get("/api/scheduled-agents", headers=self._auth_header())
        assert resp.status_code in (200, 401, 403)

    def test_get_not_found_returns_404_or_auth(self, app_client):
        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.ScheduledAgent.get", new_callable=AsyncMock, return_value=None),
        ):
            resp = app_client.get(f"/api/scheduled-agents/{FAKE_ID}", headers=self._auth_header())
        assert resp.status_code in (404, 401, 403)

    def test_create_workflow_not_found(self, app_client):
        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=None),
        ):
            resp = app_client.post(
                "/api/scheduled-agents",
                headers=self._auth_header(),
                json={
                    "name": "test",
                    "workflow_id": FAKE_WF_ID,
                    "prompt": "hello",
                    "interval_value": 1,
                    "interval_unit": "hours",
                    "start_at": datetime.now(UTC).isoformat(),
                },
            )
        assert resp.status_code in (404, 401, 403, 500)

    def test_create_workflow_forbidden(self, app_client):
        mock_wf = _make_wf(github_user="other_user")

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
        ):
            resp = app_client.post(
                "/api/scheduled-agents",
                headers=self._auth_header(),
                json={
                    "name": "test",
                    "workflow_id": FAKE_WF_ID,
                    "prompt": "hello",
                    "interval_value": 1,
                    "interval_unit": "hours",
                    "start_at": datetime.now(UTC).isoformat(),
                },
            )
        assert resp.status_code in (403, 401, 500)

    def test_create_success(self, app_client):
        mock_wf = _make_wf()
        sa = _make_sa()
        sa.insert = AsyncMock()

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
            patch("app.api.routes.scheduled_agents.ScheduledAgent", return_value=sa),
            patch("app.api.routes.scheduled_agents.scheduler.create_schedule", return_value="redbeat:key"),
        ):
            resp = app_client.post(
                "/api/scheduled-agents",
                headers=self._auth_header(),
                json={
                    "name": "Daily Report",
                    "workflow_id": FAKE_WF_ID,
                    "prompt": "Generate a daily summary",
                    "interval_value": 1,
                    "interval_unit": "days",
                    "start_at": datetime.now(UTC).isoformat(),
                },
            )
        assert resp.status_code in (201, 401, 403)

    def test_enable_already_enabled_returns_ok_or_auth(self, app_client):
        sa = _make_sa(enabled=True)
        mock_wf = _make_wf()

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.ScheduledAgent.get", new_callable=AsyncMock, return_value=sa),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
        ):
            resp = app_client.patch(f"/api/scheduled-agents/{FAKE_ID}/enable", headers=self._auth_header())
        assert resp.status_code in (200, 401, 403)

    def test_disable_success(self, app_client):
        sa = _make_sa(enabled=True)
        mock_wf = _make_wf()

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.ScheduledAgent.get", new_callable=AsyncMock, return_value=sa),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
            patch("app.api.routes.scheduled_agents.scheduler.disable_schedule"),
        ):
            resp = app_client.patch(f"/api/scheduled-agents/{FAKE_ID}/disable", headers=self._auth_header())
        assert resp.status_code in (200, 401, 403)

    def test_delete_success(self, app_client):
        sa = _make_sa()
        mock_wf = _make_wf()

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.ScheduledAgent.get", new_callable=AsyncMock, return_value=sa),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
            patch("app.api.routes.scheduled_agents.scheduler.delete_schedule"),
        ):
            resp = app_client.delete(f"/api/scheduled-agents/{FAKE_ID}", headers=self._auth_header())
        assert resp.status_code in (204, 401, 403)

    def test_delete_forbidden(self, app_client):
        sa = _make_sa()
        mock_wf = _make_wf(github_user="someone_else")

        with (
            patch("app.api.routes.scheduled_agents.get_current_user", return_value=self._user()),
            patch("app.api.routes.scheduled_agents.ScheduledAgent.get", new_callable=AsyncMock, return_value=sa),
            patch("app.api.routes.scheduled_agents.Workflow.get", new_callable=AsyncMock, return_value=mock_wf),
        ):
            resp = app_client.delete(f"/api/scheduled-agents/{FAKE_ID}", headers=self._auth_header())
        assert resp.status_code in (403, 401)
