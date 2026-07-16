"""Internal bot<->API WebSocket link for instant config-cache invalidation.

The bot is the WS client; this API is the WS server (see the FastAPI route in
app/main.py). When a settings write lands here, we broadcast an "invalidate"
message so the bot can drop its stale cached doc instead of waiting out the
Cache TTL. Auth is a shared secret compared with secrets.compare_digest — see
app/routers/*.py call sites for the domain -> collection attribute mapping,
kept in one place here (SETTINGS_DOMAIN_TO_COLLECTION) so it doesn't scatter.
"""

from __future__ import annotations

import logging

from fastapi import WebSocket

# Maps a /settings/{domain} path segment to the Database attribute name
# (see kidney-bot/utils/database.py Database.connect()) whose cache should be
# invalidated after a successful write. Keep this mapping here — the single
# source of truth — rather than duplicating it across routers.
SETTINGS_DOMAIN_TO_COLLECTION: dict[str, str] = {
    "guild_config": "guild_config",
    "heuristics": "heuristics_config",
    "heuristics_weights": "heuristics_config",
    "heuristics_thresholds": "heuristics_config",
    "automod": "automodsettings",
    "autorole": "autorolesettings",
    "moderation": "mod_config",
    "honeypot": "honeypot_config",
}


class ConnectionManager:
    """Tracks connected bot WebSocket(s) — typically exactly one — and
    broadcasts invalidation events to all of them."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    def register(self, websocket: WebSocket) -> None:
        self._connections.add(websocket)

    def unregister(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast_invalidate(self, collection: str, pk: int | str) -> None:
        message = {"type": "invalidate", "collection": collection, "pk": pk}
        for websocket in list(self._connections):
            try:
                await websocket.send_json(message)
            except Exception:
                logging.warning("Failed to send invalidate message to a bot WS connection", exc_info=True)

    async def broadcast_pong(self, websocket: WebSocket) -> None:
        try:
            await websocket.send_json({"type": "pong"})
        except Exception:
            logging.warning("Failed to send pong to a bot WS connection", exc_info=True)


manager = ConnectionManager()
