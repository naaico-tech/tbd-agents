"""Tests for app.services.token_counter."""

import pytest

from app.services.token_counter import count_tokens, estimate_messages_tokens


class TestCountTokens:
    def test_empty_string_returns_zero(self):
        assert count_tokens("") == 0

    def test_fallback_heuristic_for_unknown_model(self):
        text = "a" * 400  # 400 chars → 100 tokens via 4-char heuristic
        result = count_tokens(text, model="unknown-model-xyz")
        # Allow a 50% margin: between 50 and 200
        assert 50 <= result <= 200

    def test_short_text_nonzero(self):
        assert count_tokens("Hello world", model="") > 0

    def test_gpt4_via_tiktoken_or_fallback(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = count_tokens(text, model="gpt-4o")
        # 10-word sentence; reasonable bounds
        assert 5 <= result <= 30

    def test_claude_model_routing(self):
        text = "The quick brown fox jumps over the lazy dog."
        result = count_tokens(text, model="claude-3-5-sonnet")
        # Should not raise; any positive int is fine
        assert result > 0

    def test_long_text_scales_reasonably(self):
        text = "word " * 1000  # 5000 chars, ~1000 words
        result = count_tokens(text, model="gpt-4o")
        # tiktoken typically gives ~1100-1300 tokens for this
        assert 800 <= result <= 2000


class TestEstimateMessagesTokens:
    def test_empty_messages(self):
        assert estimate_messages_tokens([]) >= 0

    def test_single_message(self):
        msgs = [{"role": "user", "content": "Hello"}]
        result = estimate_messages_tokens(msgs)
        assert result > 0

    def test_multipart_content(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " world"},
                ],
            }
        ]
        result = estimate_messages_tokens(msgs)
        assert result > 0

    def test_more_messages_gives_more_tokens(self):
        short_msgs = [{"role": "user", "content": "Hi"}]
        long_msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello, how can I help you today?"},
            {"role": "user", "content": "Tell me about the weather in Tokyo."},
        ]
        short_count = estimate_messages_tokens(short_msgs)
        long_count = estimate_messages_tokens(long_msgs)
        assert long_count > short_count

    def test_tool_message_counted(self):
        msgs = [
            {"role": "tool", "tool_call_id": "tc1", "content": "result data here"}
        ]
        result = estimate_messages_tokens(msgs)
        assert result > 0
