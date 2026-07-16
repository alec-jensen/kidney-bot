# Dashboard link cog — connects to the web dashboard API's internal WebSocket
# endpoint (services/api app/main.py, /internal/ws) so settings writes made
# through the dashboard invalidate this bot's Cache instantly instead of
# waiting out the TTL. The bot is the WS client; the API is the WS server.
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from discord.ext import commands

from utils.kidney_bot import KidneyBot

_MIN_BACKOFF = 1.0
_MAX_BACKOFF = 60.0

# Collections whose primary key is a string id rather than an int guild_id.
# Everything else is guild-keyed and coerced to int when the wire value is a
# digit string (JSON doesn't distinguish "123" from 123 either way).
_STRING_PK_COLLECTIONS = {"networks"}


class DashboardLink(commands.Cog):
    def __init__(self, bot: KidneyBot) -> None:
        self.bot = bot
        self._task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        config = self.bot.config
        if not (config.api_internal_url and config.internal_api_secret):
            logging.info("dashboard link disabled — api_internal_url/internal_api_secret not configured")
            return
        self._task = asyncio.create_task(self._connection_loop())

    async def cog_unload(self) -> None:
        if self._task:
            self._task.cancel()

    # ── connection lifecycle ─────────────────────────────────────────────────

    async def _connection_loop(self) -> None:
        config = self.bot.config
        ws_url = config.api_internal_url.replace("https://", "wss://", 1)
        if ws_url == config.api_internal_url:  # didn't start with https://
            ws_url = ws_url.replace("http://", "ws://", 1)
        ws_url = ws_url.rstrip("/") + "/internal/ws"

        headers = {"Authorization": f"Bearer {config.internal_api_secret}"}
        backoff = _MIN_BACKOFF
        warned_this_cycle = False

        while True:
            try:
                async with aiohttp.ClientSession() as session, session.ws_connect(ws_url, headers=headers) as ws:
                    logging.info("Dashboard link: connected to %s", ws_url)
                    backoff = _MIN_BACKOFF
                    warned_this_cycle = False
                    await self._handle_connection(ws)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                if not warned_this_cycle:
                    logging.warning("Dashboard link: connection failed (%s), retrying with backoff", e)
                    warned_this_cycle = True

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF)

    async def _handle_connection(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = msg.json()
                except ValueError:
                    continue
                await self._dispatch(ws, data)
            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE):
                break

    # ── message dispatch ─────────────────────────────────────────────────────

    async def _dispatch(self, ws: aiohttp.ClientWebSocketResponse, data: dict[str, Any]) -> None:
        handler = _MESSAGE_HANDLERS.get(data.get("type"))
        if handler is not None:
            await handler(self, ws, data)

    async def _on_invalidate(self, _ws: aiohttp.ClientWebSocketResponse, data: dict[str, Any]) -> None:
        if not self.bot.database.connected:
            return

        collection_name = data.get("collection")
        collection = getattr(self.bot.database, collection_name, None) if collection_name else None
        if collection is None:
            logging.warning("Dashboard link: unknown collection %r in invalidate message", collection_name)
            return

        pk = data.get("pk")
        if isinstance(pk, str) and pk.isdigit() and collection_name not in _STRING_PK_COLLECTIONS:
            pk = int(pk)

        collection.cache.invalidate(pk)

    async def _on_ping(self, ws: aiohttp.ClientWebSocketResponse, _data: dict[str, Any]) -> None:
        await ws.send_json({"type": "pong"})

    async def _on_pong(self, _ws: aiohttp.ClientWebSocketResponse, _data: dict[str, Any]) -> None:
        pass


# Type-dispatched so future bot<->server message types slot in without
# touching _dispatch.
_MESSAGE_HANDLERS: dict[str, Any] = {
    "invalidate": DashboardLink._on_invalidate,
    "ping": DashboardLink._on_ping,
    "pong": DashboardLink._on_pong,
}


async def setup(bot: KidneyBot) -> None:
    await bot.add_cog(DashboardLink(bot))
