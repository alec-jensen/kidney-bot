from __future__ import annotations

from fastapi import APIRouter, Request

from app.auth.deps import get_session_guilds
from app.db import database

router = APIRouter(prefix="/api/guilds", tags=["guilds"])


@router.get("")
async def list_guilds(request: Request) -> list[dict]:
    """Guilds the logged-in user can manage, annotated with whether the bot is present."""
    guilds = get_session_guilds(request)
    result = []
    for guild in guilds:
        bot_guild = await database.bot_guilds.get(int(guild["id"]))
        result.append(
            {
                **guild,
                "bot_present": bot_guild is not None,
                "member_count": bot_guild.member_count if bot_guild else None,
            }
        )
    return result
