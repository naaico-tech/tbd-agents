from typing import Any

from fastapi import Header, HTTPException

from app.config import settings
from app.services.auth import validate_github_token


def _resolve_token(authorization: str | None) -> str:
    """Return the token from the header, or fall back to the env var."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if token:
            return token
    if settings.github_token:
        return settings.github_token
    raise HTTPException(
        status_code=401,
        detail="Provide an Authorization: Bearer <token> header or set GITHUB_TOKEN env var",
    )


async def get_current_user(authorization: str | None = Header(None)) -> dict[str, Any]:
    """Validate GitHub token from header (or env fallback) and return user info."""
    token = _resolve_token(authorization)
    # If the token came from the server-level env var (no Authorization header
    # provided, or the header matched the env var exactly), skip the remote
    # GitHub API call — the token is already trusted by the operator.
    is_server_token = (
        settings.github_token is not None and token == settings.github_token
    )
    return await validate_github_token(token, skip_remote=is_server_token)


def extract_token(authorization: str | None) -> str:
    """Return raw token string from header or env fallback."""
    return _resolve_token(authorization)
