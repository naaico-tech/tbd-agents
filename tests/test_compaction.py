"""Tests for message compaction and BYOK tool-loop hardening."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import (
    _clear_old_tool_results,
    _compact_messages,
)


# ── _clear_old_tool_results ──────────────────────────────────────────────────


class TestClearOldToolResults:
    def _make_messages(self, num_tool_results: int = 4, extra: int = 0) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": "sys"}]
        for i in range(num_tool_results):
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"tool result {i}"})
        for i in range(extra):
            msgs.append({"role": "user", "content": f"msg {i}"})
        return msgs

    def test_keeps_recent_n_tool_results(self):
        msgs = self._make_messages(num_tool_results=6)
        result, cleared = _clear_old_tool_results(msgs, keep_recent=3)
        assert cleared == 3
        # The last 3 tool-result messages should be unchanged
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        preserved = tool_msgs[-3:]
        for i, m in enumerate(preserved):
            assert m["content"] != "[tool result cleared for context efficiency]"
        cleared_msgs = tool_msgs[:3]
        for m in cleared_msgs:
            assert m["content"] == "[tool result cleared for context efficiency]"

    def test_keeps_all_when_fewer_than_keep_recent(self):
        msgs = self._make_messages(num_tool_results=2)
        result, cleared = _clear_old_tool_results(msgs, keep_recent=5)
        assert cleared == 0
        for m in result:
            if m.get("role") == "tool":
                assert m["content"] != "[tool result cleared for context efficiency]"

    def test_no_tool_results_returns_unchanged(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result, cleared = _clear_old_tool_results(msgs, keep_recent=2)
        assert cleared == 0
        assert result == msgs

    def test_original_list_not_mutated(self):
        msgs = self._make_messages(num_tool_results=4)
        original_contents = [m.get("content") for m in msgs if m.get("role") == "tool"]
        _clear_old_tool_results(msgs, keep_recent=2)
        # Original messages should be untouched
        current_contents = [m.get("content") for m in msgs if m.get("role") == "tool"]
        assert current_contents == original_contents

    def test_clears_all_when_keep_recent_zero(self):
        msgs = self._make_messages(num_tool_results=3)
        result, cleared = _clear_old_tool_results(msgs, keep_recent=0)
        assert cleared == 3
        for m in result:
            if m.get("role") == "tool":
                assert m["content"] == "[tool result cleared for context efficiency]"


# ── _compact_messages ────────────────────────────────────────────────────────


class TestCompactMessages:
    def _make_long_conversation(self, turns: int = 20) -> list[dict]:
        msgs: list[dict] = [{"role": "system", "content": "You are a helpful assistant."}]
        for i in range(turns):
            msgs.append({"role": "user", "content": f"User message {i}"})
            msgs.append({"role": "assistant", "content": f"Assistant reply {i}"})
        return msgs

    def test_short_list_not_compacted(self):
        msgs = self._make_long_conversation(turns=3)  # 7 messages
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = True
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 6
            result = _compact_messages(msgs)
        # ≤8 messages → returned as-is
        assert result == msgs

    def test_force_compacts_even_short_list(self):
        msgs = self._make_long_conversation(turns=3)  # 7 messages
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 4
            result = _compact_messages(msgs, force=True)
        # Force=True should trigger compaction; compaction note inserted
        contents = [m.get("content", "") for m in result]
        assert any("Context compacted" in c for c in contents)

    def test_long_list_is_compacted(self):
        msgs = self._make_long_conversation(turns=15)  # 31 messages
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 6
            result = _compact_messages(msgs)
        assert len(result) < len(msgs)
        # Compaction note should be present
        contents = [m.get("content", "") for m in result]
        assert any("Context compacted" in c for c in contents)

    def test_system_message_always_preserved(self):
        msgs = self._make_long_conversation(turns=15)
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 6
            result = _compact_messages(msgs)
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are a helpful assistant."

    def test_recent_turns_preserved(self):
        msgs = self._make_long_conversation(turns=20)
        keep_recent = 6
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = keep_recent
            result = _compact_messages(msgs)
        # Last keep_recent messages from original should appear in result tail
        original_tail = msgs[-keep_recent:]
        result_tail = result[-keep_recent:]
        for orig_msg, res_msg in zip(original_tail, result_tail):
            assert orig_msg["content"] == res_msg["content"]

    def test_tool_result_clearing_pass_runs_first(self):
        """Tool-result clearing should happen before head/tail truncation."""
        msgs: list[dict] = [{"role": "system", "content": "sys"}]
        for i in range(10):
            msgs.append({"role": "user", "content": f"q{i}"})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"result {i}"})
        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = True
            mock_settings.tool_result_clearing_keep_recent = 2
            mock_settings.compaction_keep_recent_turns = 6
            result = _compact_messages(msgs, force=True)
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        cleared = [m for m in tool_msgs if m["content"] == "[tool result cleared for context efficiency]"]
        assert len(cleared) > 0


# ── BYOK loop hardening ──────────────────────────────────────────────────────


class TestByokLoopHardening:
    """Test BYOK-specific behaviours: 429 retry and tool-execution error recovery."""

    @pytest.fixture()
    def engine(self):
        from app.core.agent_engine import AgentEngine
        return AgentEngine()

    @pytest.mark.asyncio
    async def test_tool_execution_error_returns_error_string(self, engine):
        """If a tool raises during BYOK execution, the error should be captured as a string result."""
        import httpx

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "do something"},
        ]

        tool_call = {"id": "tc1", "type": "function", "function": {"name": "broken_tool", "arguments": "{}"}}
        first_response = MagicMock()
        first_response.status_code = 200
        first_response_data = {
            "choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [tool_call]}}],
            "model": "gpt-4o",
        }
        done_response = MagicMock()
        done_response.status_code = 200
        done_response_data = {
            "choices": [{"message": {"role": "assistant", "content": "done", "tool_calls": None}}],
            "model": "gpt-4o",
        }

        mock_provider = MagicMock()
        mock_provider.api_key = "fake-key"
        mock_provider.base_url = "http://fake-provider"
        mock_provider.provider_type = "openai"

        mock_workflow = MagicMock()
        mock_workflow.model = "gpt-4o"
        mock_workflow.context_window = 128_000
        mock_workflow.temperature = 0.7
        mock_workflow.max_tokens = 1024
        mock_workflow.system_prompt = "sys"
        mock_workflow.tools = []

        call_count = 0

        async def mock_stream(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return first_response_data
            return done_response_data

        with (
            patch.object(engine, "_stream_chat_completion", side_effect=mock_stream),
            patch.object(engine, "_execute_tool", new_callable=AsyncMock, side_effect=RuntimeError("tool blew up")),
            patch.object(engine, "_resolve_tools", return_value=[]),
        ):
            result_msgs = []
            async for chunk in engine._run_with_custom_provider(
                messages=messages,
                workflow=mock_workflow,
                provider=mock_provider,
                task_execution_id="task-1",
            ):
                result_msgs.append(chunk)

        # The error should be captured and returned as a tool result, not crash
        tool_result_msgs = [m for m in result_msgs if isinstance(m, dict) and m.get("role") == "tool"]
        assert any("Tool execution error" in str(m.get("content", "")) for m in tool_result_msgs)

    @pytest.mark.asyncio
    async def test_compaction_triggered_when_tokens_exceed_threshold(self, engine):
        """_compact_messages should be called when estimated tokens exceed the threshold."""
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
        ]
        done_response = {
            "choices": [{"message": {"role": "assistant", "content": "reply", "tool_calls": None}}],
            "model": "gpt-4o",
        }
        mock_provider = MagicMock()
        mock_provider.api_key = "fake-key"
        mock_provider.base_url = "http://fake-provider"
        mock_provider.provider_type = "openai"

        mock_workflow = MagicMock()
        mock_workflow.model = "gpt-4o"
        mock_workflow.context_window = 100
        mock_workflow.temperature = 0.7
        mock_workflow.max_tokens = 50
        mock_workflow.system_prompt = "sys"
        mock_workflow.tools = []

        with (
            patch.object(engine, "_stream_chat_completion", new_callable=AsyncMock, return_value=done_response),
            patch.object(engine, "_resolve_tools", return_value=[]),
            patch("app.core.agent_engine.estimate_messages_tokens", return_value=90),
            patch("app.core.agent_engine.settings") as mock_settings,
            patch("app.core.agent_engine._compact_messages", wraps=_compact_messages) as mock_compact,
        ):
            mock_settings.compaction_enabled = True
            mock_settings.compaction_token_threshold_pct = 0.75
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 6

            result_msgs = []
            async for chunk in engine._run_with_custom_provider(
                messages=messages,
                workflow=mock_workflow,
                provider=mock_provider,
                task_execution_id="task-1",
            ):
                result_msgs.append(chunk)

        mock_compact.assert_called()
