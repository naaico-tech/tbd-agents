"""Tests for message compaction and BYOK tool-loop hardening."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.agent_engine import (
    _clear_old_tool_results,
    _compact_messages,
    _execute_custom_tool,
    _execute_mcp_tool,
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
        """_clear_old_tool_results is invoked inside _compact_messages when enabled."""
        msgs: list[dict] = [{"role": "system", "content": "sys"}]
        for i in range(10):
            msgs.append({"role": "user", "content": f"q{i}"})
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
            msgs.append({"role": "tool", "tool_call_id": f"c{i}", "content": f"result {i}"})

        with (
            patch("app.core.agent_engine.settings") as mock_settings,
            patch("app.core.agent_engine._clear_old_tool_results", wraps=_clear_old_tool_results) as mock_clear,
        ):
            mock_settings.tool_result_clearing_enabled = True
            mock_settings.tool_result_clearing_keep_recent = 2
            mock_settings.compaction_keep_recent_turns = 6
            _compact_messages(msgs, force=True)
        mock_clear.assert_called_once_with(msgs, 2)


# ── BYOK tool-execution helpers ──────────────────────────────────────────────


class TestByokToolHelpers:
    """Unit tests for the BYOK tool-execution helper functions."""

    @pytest.mark.asyncio
    async def test_execute_custom_tool_returns_json_error_when_not_found(self):
        """_execute_custom_tool returns a JSON error when tool is not in the map."""
        import json
        result = await _execute_custom_tool("missing_tool", {}, {})
        data = json.loads(result)
        assert "error" in data
        assert "missing_tool" in data["error"]

    @pytest.mark.asyncio
    async def test_execute_mcp_tool_returns_json_error_when_not_found(self):
        """_execute_mcp_tool returns a JSON error when server is not in the map."""
        import json
        result = await _execute_mcp_tool("unknown_tool", {}, {})
        data = json.loads(result)
        assert "error" in data

    @pytest.mark.asyncio
    async def test_custom_tool_runner_exception_is_propagated(self):
        """If the custom tool runner raises, the exception propagates (caller wraps it)."""
        tool_mock = MagicMock()
        tool_mock.env_config = None
        tool_mock.source_code = "print('hi')"
        tool_mock.name = "my_tool"

        with patch(
            "app.core.agent_engine.custom_tool_runner.run_tool",
            new_callable=AsyncMock,
            side_effect=RuntimeError("runner failed"),
        ):
            with pytest.raises(RuntimeError, match="runner failed"):
                await _execute_custom_tool("my_tool", {}, {"my_tool": tool_mock})

    def test_compact_messages_inserts_exactly_one_note(self):
        """Exactly one compaction note is inserted per compaction pass."""
        msgs = [{"role": "system", "content": "sys"}]
        for i in range(20):
            msgs.append({"role": "user", "content": f"q{i}"})
            msgs.append({"role": "assistant", "content": f"a{i}"})

        with patch("app.core.agent_engine.settings") as mock_settings:
            mock_settings.tool_result_clearing_enabled = False
            mock_settings.tool_result_clearing_keep_recent = 4
            mock_settings.compaction_keep_recent_turns = 4
            result = _compact_messages(msgs)

        notes = [m for m in result if "Context compacted" in m.get("content", "")]
        assert len(notes) == 1
