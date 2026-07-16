from __future__ import annotations

from fastapi import HTTPException, Request


def get_session_guilds(request: Request) -> list[dict]:
    if request.session.get("user") is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return request.session.get("guilds", [])


def require_guild_access(request: Request, guild_id: int) -> None:
    guilds = get_session_guilds(request)
    if not any(int(g["id"]) == guild_id for g in guilds):
        raise HTTPException(status_code=403, detail="You do not have access to this guild")
