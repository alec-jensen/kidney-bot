"""Thin wrapper around the Discord OAuth2 + REST endpoints needed for login."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import get_config

DISCORD_API = "https://discord.com/api/v10"

# Relevant Discord guild permission bits (see Discord's permissions bitfield docs).
PERMISSION_ADMINISTRATOR = 0x8
PERMISSION_MANAGE_GUILD = 0x20


def authorize_url(state: str) -> str:
    cfg = get_config()
    params = {
        "client_id": cfg.discord_client_id,
        "redirect_uri": cfg.discord_redirect_uri,
        "response_type": "code",
        "scope": "identify guilds",
        "state": state,
        "prompt": "none",
    }
    return f"https://discord.com/oauth2/authorize?{urlencode(params)}"


async def exchange_code(code: str) -> dict[str, Any]:
    cfg = get_config()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{DISCORD_API}/oauth2/token",
            data={
                "client_id": cfg.discord_client_id,
                "client_secret": cfg.discord_client_secret,
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg.discord_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_manageable_guilds(access_token: str) -> list[dict[str, Any]]:
    """Guilds where the user has Manage Server or Administrator."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        guilds = resp.json()

    manageable = []
    for guild in guilds:
        permissions = int(guild.get("permissions", 0))
        if permissions & (PERMISSION_ADMINISTRATOR | PERMISSION_MANAGE_GUILD):
            manageable.append(
                {
                    "id": guild["id"],
                    "name": guild["name"],
                    "icon": guild.get("icon"),
                }
            )
    return manageable
