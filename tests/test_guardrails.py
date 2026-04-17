"""Tests for the guardrails enforcement engine."""

import json

import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock

from app.core.guardrails import _check_output, _check_prompt, _check_request
from app.models.guardrail import (
    GuardrailType,
    OutputGuardrailConfig,
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


# ── Output guardrail checks ─────────────────────────────────────────────────


def _make_output_guardrail(**kwargs):
    """Build a mock Guardrail with output config, avoiding Beanie init."""
    g = MagicMock()
    g.name = "output-guard"
    g.guardrail_type = GuardrailType.OUTPUT
    g.output_config = OutputGuardrailConfig(**kwargs)
    g.prompt_config = None
    g.request_config = None
    return g


class TestOutputGuardrails:
    def test_passes_clean_output(self):
        g = _make_output_guardrail(max_length=500)
        assert _check_output("Hello, world!", g) is None

    def test_rejects_too_long_output(self):
        g = _make_output_guardrail(max_length=10)
        result = _check_output("This is way too long for the limit", g)
        assert result is not None
        assert "too long" in result

    def test_rejects_forbidden_pattern_in_output(self):
        g = _make_output_guardrail(forbidden_patterns=[r"password|secret"])
        result = _check_output("The password is hunter2", g)
        assert result is not None
        assert "forbidden pattern" in result

    def test_allows_output_without_forbidden_match(self):
        g = _make_output_guardrail(forbidden_patterns=[r"password|secret"])
        assert _check_output("The weather is nice today", g) is None

    def test_rejects_missing_required_pattern(self):
        g = _make_output_guardrail(required_patterns=[r"\bsummary\b"])
        result = _check_output("Here is the result", g)
        assert result is not None
        assert "required pattern" in result

    def test_passes_required_pattern(self):
        g = _make_output_guardrail(required_patterns=[r"\bsummary\b"])
        assert _check_output("Here is the summary of findings", g) is None

    def test_rejects_invalid_json_when_required(self):
        g = _make_output_guardrail(must_be_valid_json=True)
        result = _check_output("this is not json", g)
        assert result is not None
        assert "not valid JSON" in result

    def test_passes_valid_json_when_required(self):
        g = _make_output_guardrail(must_be_valid_json=True)
        assert _check_output('{"key": "value"}', g) is None

    def test_detects_email_pii(self):
        g = _make_output_guardrail(pii_detection=True)
        result = _check_output("Contact us at user@example.com", g)
        assert result is not None
        assert "PII" in result
        assert "email" in result

    def test_detects_phone_pii(self):
        g = _make_output_guardrail(pii_detection=True)
        result = _check_output("Call us at (555) 123-4567", g)
        assert result is not None
        assert "PII" in result

    def test_detects_ssn_pii(self):
        g = _make_output_guardrail(pii_detection=True)
        result = _check_output("SSN is 123-45-6789", g)
        assert result is not None
        assert "PII" in result

    def test_no_pii_passes(self):
        g = _make_output_guardrail(pii_detection=True)
        assert _check_output("No personal information here", g) is None

    def test_no_config_passes(self):
        g = MagicMock()
        g.name = "noop-output"
        g.output_config = None
        assert _check_output("anything", g) is None

    def test_multiple_violations_first_returned(self):
        g = _make_output_guardrail(max_length=5, forbidden_patterns=[r"test"])
        result = _check_output("test string", g)
        assert result is not None
        # max_length is checked first
        assert "too long" in result
