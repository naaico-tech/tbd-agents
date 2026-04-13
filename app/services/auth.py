from typing import Any

import httpx
from fastapi import HTTPException


async def validate_github_token(token: str) -> dict[str, Any]:
    """Validate a GitHub PAT by calling the GitHub Users API. Returns user info."""
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
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired GitHub token")
    data = resp.json()
    return {"login": data["login"], "id": data["id"], "name": data.get("name")}
