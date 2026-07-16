from __future__ import annotations

import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.auth.routes import router as auth_router
from app.config import get_config
from app.db import database
from app.routers.discord_meta import router as discord_meta_router
from app.routers.docs import router as docs_router
from app.routers.guilds import router as guilds_router
from app.routers.honeypot import router as honeypot_router
from app.routers.lists import router as lists_router
from app.routers.network import router as network_router
from app.routers.settings import router as settings_router
from app.ws import manager as ws_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    if database.connected:
        await database.client.close()  # type: ignore[attr-defined]


app = FastAPI(title="kidney-bot dashboard API", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=get_config().session_secret)

frontend_url = get_config().dashboard_frontend_url
if frontend_url:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth_router)
app.include_router(guilds_router)
app.include_router(settings_router)
app.include_router(network_router)
app.include_router(lists_router)
app.include_router(discord_meta_router)
app.include_router(honeypot_router)
app.include_router(docs_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "database_connected": database.connected}


@app.websocket("/internal/ws")
async def internal_ws(websocket: WebSocket) -> None:
    """Bot<->API internal link. The bot connects as a client; we push
    "invalidate" events after settings writes so its Cache drops stale docs
    immediately instead of waiting out the TTL. Auth is a shared secret —
    when unset, all connections are rejected."""
    secret = get_config().internal_api_secret
    auth_header = websocket.headers.get("authorization", "")
    provided = auth_header.removeprefix("Bearer ") if auth_header.startswith("Bearer ") else ""

    if not secret or not secrets.compare_digest(provided, secret):
        await websocket.close(code=4401)
        return

    await websocket.accept()
    ws_manager.register(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await ws_manager.broadcast_pong(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.unregister(websocket)
