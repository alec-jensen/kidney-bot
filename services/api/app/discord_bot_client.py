"""Bot-token-authenticated Discord REST calls.

Plain HTTP against Discord's REST API using the bot's own token — no gateway
connection, same as any REST-only integration would do. Used to power
channel/role pickers and to perform the one honeypot action (posting the
verify message) that can't be expressed as a plain settings write.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_config

DISCORD_API = "https://discord.com/api/v10"

# Channel types that can receive messages (text, announcement, forum, and
# their thread/voice-text variants) — the only kinds worth offering in a
# "pick a channel to post/log to" dropdown.
_TEXT_CHANNEL_TYPES = {0, 5, 15}


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bot {get_config().bot_token}"}


async def list_channels(guild_id: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{DISCORD_API}/guilds/{guild_id}/channels", headers=_headers())
        resp.raise_for_status()
        channels = resp.json()
    return [
        {"id": c["id"], "name": c["name"], "type": c["type"], "position": c.get("position", 0)}
        for c in channels
        if c["type"] in _TEXT_CHANNEL_TYPES
    ]


async def list_roles(guild_id: int) -> list[dict[str, Any]]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{DISCORD_API}/guilds/{guild_id}/roles", headers=_headers())
        resp.raise_for_status()
        roles = resp.json()
    return [
        {"id": r["id"], "name": r["name"], "color": r.get("color", 0), "position": r.get("position", 0)}
        for r in roles
        if r["name"] != "@everyone"
    ]


async def send_message(
    channel_id: int,
    *,
    embed: dict[str, Any],
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DISCORD_API}/channels/{channel_id}/messages",
            headers=_headers(),
            json={"embeds": [embed], "components": components or []},
        )
        resp.raise_for_status()
        return resp.json()


async def delete_message(channel_id: int, message_id: int) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{DISCORD_API}/channels/{channel_id}/messages/{message_id}",
            headers=_headers(),
        )
        resp.raise_for_status()
