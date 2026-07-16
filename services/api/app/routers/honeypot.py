"""The one honeypot operation that can't be a plain settings write: enabling
in a channel requires actually posting the verify message with its persistent
button (see kidney-bot/cogs/honeypot.py's HoneypotVerifyView — routing is by
custom_id, so a message posted here works identically once the bot process
picks up the click).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from utils.database import Schemas

from app.auth.deps import require_guild_access
from app.db import database
from app.discord_bot_client import delete_message, send_message
from app.ws import manager as ws_manager

router = APIRouter(prefix="/api/guilds/{guild_id}/honeypot", tags=["honeypot"])

_VERIFY_EMBED = {
    "title": "⚠️  Verification Required",
    "description": (
        "Welcome! To access this server you must verify that you're a real person.\n\n"
        "**Click the button below to gain access.**\n\n"
        "⛔ **Warning:** Sending any message in this channel will be treated as automated "
        "bot activity and will result in immediate action (mute, kick, or ban). "
        "This channel is an automated honeypot."
    ),
    "color": 0xE67E22,
    "footer": {"text": "Automated verification • kidney bot"},
}

_VERIFY_BUTTON_COMPONENTS = [
    {
        "type": 1,
        "components": [
            {
                "type": 2,
                "style": 3,
                "label": "I'm a real person",
                "custom_id": "honeypot:verify",
                "emoji": {"name": "✅"},
            }
        ],
    }
]


class EnableRequest(BaseModel):
    channel_id: str
    mode: str = "visibility"
    action: str = "kick"


@router.post("/enable")
async def enable_honeypot(guild_id: int, request: Request, body: EnableRequest) -> dict:
    require_guild_access(request, guild_id)
    if body.mode not in ("visibility", "lockdown"):
        raise HTTPException(status_code=400, detail="mode must be 'visibility' or 'lockdown'")
    if body.action not in ("kick", "ban", "mute"):
        raise HTTPException(status_code=400, detail="action must be 'kick', 'ban', or 'mute'")

    channel_id = int(body.channel_id)

    cfg = await database.honeypot_config.get(guild_id) or Schemas.HoneypotConfig(guild_id=guild_id)

    # Clean up the previous verify message, if any — the old channel may differ
    # from the new one, so resolve it from the pre-update cfg. Never let this
    # block re-enabling: the old message may already be gone, or permissions
    # may have changed.
    if cfg.message_id and cfg.channel_id:
        try:
            await delete_message(cfg.channel_id, cfg.message_id)
        except httpx.HTTPStatusError:
            pass

    try:
        message = await send_message(channel_id, embed=_VERIFY_EMBED, components=_VERIFY_BUTTON_COMPONENTS)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to post verification message (does the bot have Send Messages there?): {e}"
        )

    cfg.channel_id = channel_id
    cfg.mode = body.mode
    cfg.message_action = body.action
    cfg.message_id = int(message["id"])
    cfg.enabled = True
    await database.honeypot_config.save(cfg)
    await ws_manager.broadcast_invalidate("honeypot_config", guild_id)
    return {
        "enabled": True,
        "channel_id": str(channel_id),
        "mode": body.mode,
        "message_action": body.action,
    }


@router.post("/disable")
async def disable_honeypot(guild_id: int, request: Request) -> dict:
    require_guild_access(request, guild_id)
    cfg = await database.honeypot_config.get(guild_id) or Schemas.HoneypotConfig(guild_id=guild_id)
    cfg.enabled = False
    await database.honeypot_config.save(cfg)
    await ws_manager.broadcast_invalidate("honeypot_config", guild_id)
    return {"enabled": False}
