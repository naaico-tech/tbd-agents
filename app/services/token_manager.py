"""Encrypted token storage and runtime injection for MCP server configs.

Tokens are Fernet-encrypted at rest in MongoDB. The ``resolve_config``
function deep-walks a dict and substitutes ``{{token:NAME}}`` references
with decrypted values, enabling MCP connection configs to reference
secrets by name instead of storing plaintext credentials.
"""

import copy
import logging
import re
from datetime import UTC, datetime
from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import settings
from app.models.token import Token

logger = logging.getLogger(__name__)

_TOKEN_REF_RE = re.compile(r"\{\{token:([^}]+)\}\}")


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    """Return a cached Fernet instance using the configured encryption key."""
    key = settings.token_encryption_key
    if not key:
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY is not set. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return a URL-safe base64-encoded token."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a Fernet-encrypted string back to plaintext."""
    return _get_fernet().decrypt(encrypted.encode()).decode()


def mask_value(encrypted: str) -> str:
    """Decrypt and return a masked version showing only the last 4 characters."""
    try:
        plain = decrypt_value(encrypted)
        if len(plain) <= 4:
            return "****"
        return "..." + plain[-4:]
    except Exception:
        return "****"


# ── CRUD ─────────────────────────────────────────────────────────────────────


async def create_token(
    name: str, value: str, description: str, created_by: str
) -> Token:
    """Create a new encrypted token. Raises ValueError if name already exists."""
    existing = await Token.find_one(Token.name == name)
    if existing:
        raise ValueError(f"Token with name '{name}' already exists")
    token = Token(
        name=name,
        encrypted_value=encrypt_value(value),
        description=description,
        created_by=created_by,
    )
    await token.insert()
    return token


async def get_token_value(name: str) -> str | None:
    """Fetch a token by name and return the decrypted plaintext, or None."""
    token = await Token.find_one(Token.name == name)
    if not token:
        return None
    return decrypt_value(token.encrypted_value)


async def list_tokens() -> list[Token]:
    """Return all tokens (values remain encrypted — use mask_value for display)."""
    return await Token.find_all().to_list()


async def update_token(
    token: Token,
    value: str | None = None,
    description: str | None = None,
) -> Token:
    """Update a token's value and/or description."""
    if value is not None:
        token.encrypted_value = encrypt_value(value)
    if description is not None:
        token.description = description
    token.updated_at = datetime.now(UTC)
    await token.save()
    return token


async def delete_token(token: Token) -> None:
    """Delete a token document."""
    await token.delete()


# ── Runtime config resolution ────────────────────────────────────────────────


async def resolve_config(config: dict) -> dict:
    """Deep-walk *config* and replace every ``{{token:NAME}}`` reference.

    - Supports full-value references: ``"{{token:my-key}}"`` → ``"actual_secret"``
    - Supports partial/embedded references: ``"Bearer {{token:notion}}"`` →
      ``"Bearer ntn_abc..."``
    - Unresolved references (token not found) are left in place with a warning.
    - Returns a **new** dict; the original is not mutated.
    """
    # Collect all referenced token names first to batch-fetch
    refs: set[str] = set()
    _collect_refs(config, refs)
    if not refs:
        return config

    # Batch-fetch and decrypt
    resolved: dict[str, str] = {}
    for name in refs:
        value = await get_token_value(name)
        if value is not None:
            resolved[name] = value
        else:
            logger.warning("Token reference '{{token:%s}}' not found in store", name)

    if not resolved:
        return config

    return _substitute(copy.deepcopy(config), resolved)


def _collect_refs(obj, refs: set[str]) -> None:
    """Recursively collect all ``{{token:NAME}}`` references in *obj*."""
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_refs(item, refs)
    elif isinstance(obj, str):
        for match in _TOKEN_REF_RE.finditer(obj):
            refs.add(match.group(1))


def _substitute(obj, resolved: dict[str, str]):
    """Recursively substitute resolved token values in *obj* (in-place on deep copy)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            obj[k] = _substitute(v, resolved)
        return obj
    elif isinstance(obj, list):
        return [_substitute(item, resolved) for item in obj]
    elif isinstance(obj, str):
        if not _TOKEN_REF_RE.search(obj):
            return obj
        # Replace all occurrences
        def replacer(m):
            name = m.group(1)
            return resolved.get(name, m.group(0))  # leave unresolved as-is
        return _TOKEN_REF_RE.sub(replacer, obj)
    return obj
