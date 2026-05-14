from typing import Any

import httpx
from fastapi import HTTPException


async def validate_github_token(token: str, *, skip_remote: bool = False) -> dict[str, Any]:
    """Validate a GitHub PAT by calling the GitHub Users API. Returns user info.

    When *skip_remote* is True the network call is skipped and a synthetic user
    is returned.  This is used for the server-level GITHUB_TOKEN which is
    already trusted (configured by the operator) and avoids a network round-trip
    to api.github.com that would fail in air-gapped / Docker environments.
    """
    if skip_remote:
        return {"login": "server", "id": 0, "name": "Server Token"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10.0,
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=503,
            detail="GitHub API unreachable (timeout). Check network connectivity.",
        )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"GitHub API unreachable: {exc}",
        )

    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired GitHub token")
    data = resp.json()
    return {"login": data["login"], "id": data["id"], "name": data.get("name")}
