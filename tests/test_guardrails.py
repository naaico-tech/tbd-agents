"""Tests for the guardrails enforcement engine."""

import json

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from app.core.guardrails import _check_prompt, _check_request
from app.models.guardrail import (
    GuardrailType,
    PromptGuardrailConfig,
    RequestGuardrailConfig,
)


def _make_prompt_guardrail(**kwargs):
    """Build a mock Guardrail with prompt config, avoiding Beanie init."""
    g = MagicMock()
    g.name = "test-guardrail"
    g.guardrail_type = GuardrailType.PROMPT
    g.prompt_config = PromptGuardrailConfig(**kwargs)
    g.request_config = None
    return g


def _make_request_guardrail(schema: dict):
    """Build a mock Guardrail with request config, avoiding Beanie init."""
    g = MagicMock()
    g.name = "schema-check"
    g.guardrail_type = GuardrailType.REQUEST
    g.request_config = RequestGuardrailConfig(json_schema=schema)
    g.prompt_config = None
    return g


# ── Prompt guardrail checks ─────────────────────────────────────────────────


class TestPromptGuardrails:
    def test_passes_valid_prompt(self):
        g = _make_prompt_guardrail(min_length=3, max_length=100)
        _check_prompt("Hello, world!", g)  # should not raise

    def test_rejects_too_short(self):
        g = _make_prompt_guardrail(min_length=10)
        with pytest.raises(HTTPException) as exc_info:
            _check_prompt("Hi", g)
        assert exc_info.value.status_code == 422
        assert "too short" in exc_info.value.detail

    def test_rejects_too_long(self):
        g = _make_prompt_guardrail(max_length=5)
        with pytest.raises(HTTPException) as exc_info:
            _check_prompt("This is way too long", g)
        assert exc_info.value.status_code == 422
        assert "too long" in exc_info.value.detail

    def test_rejects_forbidden_pattern(self):
        g = _make_prompt_guardrail(forbidden_patterns=[r"password|secret"])
        with pytest.raises(HTTPException) as exc_info:
            _check_prompt("Please share the password", g)
        assert exc_info.value.status_code == 422
        assert "forbidden pattern" in exc_info.value.detail

    def test_allows_prompt_without_forbidden_match(self):
        g = _make_prompt_guardrail(forbidden_patterns=[r"password|secret"])
        _check_prompt("Tell me about Python", g)  # should not raise

    def test_rejects_missing_required_pattern(self):
        g = _make_prompt_guardrail(required_patterns=[r"@required"])
        with pytest.raises(HTTPException) as exc_info:
            _check_prompt("No required marker here", g)
        assert exc_info.value.status_code == 422
        assert "required pattern" in exc_info.value.detail

    def test_passes_required_pattern(self):
        g = _make_prompt_guardrail(required_patterns=[r"@required"])
        _check_prompt("@required Do this", g)  # should not raise

    def test_no_config_passes(self):
        """Guardrail with empty prompt_config should not raise."""
        g = _make_prompt_guardrail()
        _check_prompt("anything", g)

    def test_none_prompt_config_passes(self):
        """Guardrail with None prompt_config should not raise."""
        g = MagicMock()
        g.name = "noop"
        g.prompt_config = None
        _check_prompt("anything", g)

    def test_case_insensitive_forbidden(self):
        g = _make_prompt_guardrail(forbidden_patterns=[r"DELETE"])
        with pytest.raises(HTTPException):
            _check_prompt("please delete this", g)

    def test_multiple_forbidden_patterns(self):
        g = _make_prompt_guardrail(forbidden_patterns=[r"alpha", r"beta"])
        with pytest.raises(HTTPException):
            _check_prompt("test beta value", g)
        with pytest.raises(HTTPException):
            _check_prompt("test alpha value", g)
        _check_prompt("test gamma value", g)


# ── Request guardrail checks ────────────────────────────────────────────────


class TestRequestGuardrails:
    def test_valid_request(self):
        schema = {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        }
        g = _make_request_guardrail(schema)
        _check_request({"query": "test"}, g)  # should not raise

    def test_invalid_request_missing_field(self):
        schema = {
            "type": "object",
            "required": ["query"],
            "properties": {"query": {"type": "string"}},
        }
        g = _make_request_guardrail(schema)
        with pytest.raises(HTTPException) as exc_info:
            _check_request({}, g)
        assert exc_info.value.status_code == 422
        assert "request validation failed" in exc_info.value.detail

    def test_invalid_request_wrong_type(self):
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        g = _make_request_guardrail(schema)
        with pytest.raises(HTTPException):
            _check_request({"count": "not-a-number"}, g)

    def test_no_config_passes(self):
        """Guardrail with None request_config should not raise."""
        g = MagicMock()
        g.name = "noop-request"
        g.request_config = None
        _check_request({"anything": True}, g)

    def test_nested_schema_validation(self):
        schema = {
            "type": "object",
            "required": ["user"],
            "properties": {
                "user": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"}},
                }
            },
        }
        g = _make_request_guardrail(schema)
        _check_request({"user": {"name": "Alice"}}, g)
        with pytest.raises(HTTPException):
            _check_request({"user": {}}, g)
