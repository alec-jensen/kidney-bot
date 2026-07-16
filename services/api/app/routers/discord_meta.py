"""Discord channel/role listings, fetched via the bot token's REST access —
powers the dashboard's channel/role picker dropdowns instead of raw ID inputs.
"""

from __future__ import annotations

from typing import NoReturn

import httpx
from fastapi import APIRouter, HTTPException, Request

from app.auth.deps import require_guild_access
from app.discord_bot_client import list_channels, list_roles

router = APIRouter(prefix="/api/guilds/{guild_id}", tags=["discord-meta"])


def _raise_discord_error(e: httpx.HTTPStatusError, what: str) -> NoReturn:
    raise HTTPException(
        status_code=502,
        detail=f"Discord API error fetching {what} (is the bot in this guild?): {e.response.status_code}",
    )


@router.get("/channels")
async def get_channels(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    try:
        return await list_channels(guild_id)
    except httpx.HTTPStatusError as e:
        _raise_discord_error(e, "channels")


@router.get("/roles")
async def get_roles(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    try:
        return await list_roles(guild_id)
    except httpx.HTTPStatusError as e:
        _raise_discord_error(e, "roles")
