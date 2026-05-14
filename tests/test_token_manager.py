"""Tests for the token manager (encryption, decryption, config resolution)."""

from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet

from app.services.token_manager import (
    _TOKEN_REF_RE,
    _collect_refs,
    _substitute,
    decrypt_value,
    encrypt_value,
    find_unresolved_tokens,
    mask_value,
)

# Generate a real Fernet key for testing
_TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def _patch_settings():
    """Patch the encryption key for all tests in this module."""
    with patch("app.services.token_manager.settings") as mock_settings:
        mock_settings.token_encryption_key = _TEST_KEY
        # Clear the lru_cache so each test gets a fresh Fernet instance
        from app.services.token_manager import _get_fernet
        _get_fernet.cache_clear()
        yield mock_settings
        _get_fernet.cache_clear()


class TestEncryptDecrypt:
    def test_round_trip(self):
        plaintext = "super-secret-token-12345"
        encrypted = encrypt_value(plaintext)
        assert encrypted != plaintext
        decrypted = decrypt_value(encrypted)
        assert decrypted == plaintext

    def test_different_encryptions(self):
        """Fernet uses random IV, so same plaintext produces different ciphertext."""
        p = "same-text"
        e1 = encrypt_value(p)
        e2 = encrypt_value(p)
        assert e1 != e2  # different ciphertexts
        assert decrypt_value(e1) == decrypt_value(e2) == p

    def test_empty_string(self):
        encrypted = encrypt_value("")
        assert decrypt_value(encrypted) == ""

    def test_unicode(self):
        plaintext = "tøken-wïth-únïcödé-🔐"
        encrypted = encrypt_value(plaintext)
        assert decrypt_value(encrypted) == plaintext


class TestMaskValue:
    def test_mask_shows_last_four(self):
        encrypted = encrypt_value("ghp_abcdef1234")
        masked = mask_value(encrypted)
        assert masked == "...1234"

    def test_mask_short_value(self):
        encrypted = encrypt_value("abc")
        masked = mask_value(encrypted)
        assert masked == "****"

    def test_mask_four_char_value(self):
        encrypted = encrypt_value("abcd")
        masked = mask_value(encrypted)
        assert masked == "****"

    def test_mask_five_char_value(self):
        encrypted = encrypt_value("abcde")
        masked = mask_value(encrypted)
        assert masked == "...bcde"

    def test_mask_invalid_encrypted(self):
        assert mask_value("not-valid-fernet") == "****"


class TestTokenRefRegex:
    def test_matches_simple_ref(self):
        m = _TOKEN_REF_RE.search("{{token:my-key}}")
        assert m is not None
        assert m.group(1) == "my-key"

    def test_matches_embedded_ref(self):
        m = _TOKEN_REF_RE.search("Bearer {{token:notion}}")
        assert m.group(1) == "notion"

    def test_no_match(self):
        m = _TOKEN_REF_RE.search("no tokens here")
        assert m is None

    def test_multiple_refs(self):
        text = "{{token:a}} and {{token:b}}"
        matches = _TOKEN_REF_RE.findall(text)
        assert matches == ["a", "b"]


class TestCollectRefs:
    def test_dict_refs(self):
        refs = set()
        _collect_refs({"key": "{{token:abc}}", "nested": {"key2": "{{token:def}}"}}, refs)
        assert refs == {"abc", "def"}

    def test_list_refs(self):
        refs = set()
        _collect_refs(["{{token:x}}", "plain", "{{token:y}}"], refs)
        assert refs == {"x", "y"}

    def test_no_refs(self):
        refs = set()
        _collect_refs({"key": "value", "num": 42}, refs)
        assert refs == set()

    def test_mixed_types(self):
        refs = set()
        _collect_refs({"a": "{{token:t1}}", "b": 123, "c": None, "d": True}, refs)
        assert refs == {"t1"}


class TestSubstitute:
    def test_full_value_replacement(self):
        result = _substitute(
            {"auth": "{{token:key1}}"},
            {"key1": "secret123"},
        )
        assert result == {"auth": "secret123"}

    def test_partial_replacement(self):
        result = _substitute(
            {"header": "Bearer {{token:tok}}"},
            {"tok": "abc"},
        )
        assert result == {"header": "Bearer abc"}

    def test_unresolved_left_in_place(self):
        result = _substitute(
            {"auth": "{{token:missing}}"},
            {},
        )
        assert result == {"auth": "{{token:missing}}"}

    def test_nested_dict(self):
        result = _substitute(
            {"outer": {"inner": "{{token:k}}"}},
            {"k": "v"},
        )
        assert result == {"outer": {"inner": "v"}}

    def test_list_substitution(self):
        result = _substitute(
            ["{{token:a}}", "plain", "{{token:b}}"],
            {"a": "1", "b": "2"},
        )
        assert result == ["1", "plain", "2"]

    def test_non_string_passthrough(self):
        result = _substitute({"num": 42, "flag": True}, {})
        assert result == {"num": 42, "flag": True}

    def test_multiple_refs_in_one_string(self):
        result = _substitute(
            {"combined": "{{token:user}}:{{token:pass}}"},
            {"user": "admin", "pass": "s3cret"},
        )
        assert result == {"combined": "admin:s3cret"}


class TestFindUnresolvedTokens:
    def test_empty_dict_returns_empty_set(self):
        assert find_unresolved_tokens({}) == set()

    def test_fully_resolved_returns_empty_set(self):
        # Simulate a resolved env config where all {{token:...}} were replaced.
        resolved = {"API_KEY": "actual-secret", "TIMEOUT": "30"}
        assert find_unresolved_tokens(resolved) == set()

    def test_single_unresolved_token(self):
        # token was not found in the store — placeholder left in place
        resolved = {"CREDS_JSON": "{{token:google-sheets-credentials}}"}
        assert find_unresolved_tokens(resolved) == {"google-sheets-credentials"}

    def test_multiple_unresolved_tokens(self):
        resolved = {
            "KEY_A": "{{token:token-a}}",
            "KEY_B": "{{token:token-b}}",
        }
        assert find_unresolved_tokens(resolved) == {"token-a", "token-b"}

    def test_mixed_resolved_and_unresolved(self):
        resolved = {
            "RESOLVED_KEY": "real-value",
            "MISSING_KEY": "{{token:missing-cred}}",
        }
        assert find_unresolved_tokens(resolved) == {"missing-cred"}

    def test_partial_substitution_in_string(self):
        # e.g. "Bearer {{token:tok}}" where the token was not found
        resolved = {"AUTH": "Bearer {{token:my-token}}"}
        assert find_unresolved_tokens(resolved) == {"my-token"}

    def test_nested_dict_unresolved(self):
        resolved = {"outer": {"inner": "{{token:nested-tok}}"}}
        assert find_unresolved_tokens(resolved) == {"nested-tok"}
