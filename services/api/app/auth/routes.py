from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from app.auth.discord_client import (
    authorize_url,
    exchange_code,
    fetch_manageable_guilds,
    fetch_user,
)
from app.config import get_config

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    request.session["oauth_state"] = state
    return RedirectResponse(authorize_url(state))


@router.get("/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    expected_state = request.session.pop("oauth_state", None)
    if not expected_state or not secrets.compare_digest(expected_state, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    token_data = await exchange_code(code)
    access_token = token_data["access_token"]

    user = await fetch_user(access_token)
    guilds = await fetch_manageable_guilds(access_token)

    request.session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "avatar": user.get("avatar"),
    }
    request.session["guilds"] = guilds

    frontend_url = get_config().dashboard_frontend_url
    if frontend_url:
        return RedirectResponse(frontend_url)
    return RedirectResponse("/auth/me")


@router.get("/me")
async def me(request: Request) -> dict:
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return {"user": user, "guilds": request.session.get("guilds", [])}


@router.post("/logout")
async def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}
