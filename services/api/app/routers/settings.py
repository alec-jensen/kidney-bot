from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.auth.deps import require_guild_access
from app.db import database
from app.settings.registry import DOMAINS
from app.settings.types import apply_updates, get_effective_settings, to_schema_dicts
from app.ws import SETTINGS_DOMAIN_TO_COLLECTION
from app.ws import manager as ws_manager

router = APIRouter(prefix="/api/guilds/{guild_id}", tags=["settings"])

# Manually listed alongside DOMAINS since it needs bespoke resolution/ownership —
# see app/routers/network.py. Frontend routes to /network instead of /settings/network.
_NETWORK_INDEX_ENTRY = {
    "key": "network",
    "label": "Network",
    "description": "Cross-server ban/kick/mute sync and shared reputation. Only editable by the network owner.",
    "special": "network",
    "resettable": False,
}


@router.get("/settings")
async def list_settings_domains(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    domains = [
        {
            "key": d.key,
            "label": d.label,
            "description": d.description,
            "special": None,
            "resettable": bool(d.reset_sources),
        }
        for d in DOMAINS.values()
    ]
    domains.append(_NETWORK_INDEX_ENTRY)
    return domains


def _get_domain(domain: str):
    spec = DOMAINS.get(domain)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown settings domain: {domain}")
    return spec


@router.get("/settings-schema/{domain}")
async def get_domain_schema(guild_id: int, domain: str, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    spec = _get_domain(domain)
    return to_schema_dicts(spec.fields)


@router.get("/settings/{domain}")
async def get_domain_settings(guild_id: int, domain: str, request: Request) -> dict:
    require_guild_access(request, guild_id)
    spec = _get_domain(domain)
    obj = await spec.load(database, guild_id)
    return get_effective_settings(obj, spec.fields)


@router.patch("/settings/{domain}")
async def patch_domain_settings(
    guild_id: int,
    domain: str,
    request: Request,
    updates: dict[str, bool | int | float | str | None],
) -> dict:
    require_guild_access(request, guild_id)
    spec = _get_domain(domain)
    obj = await spec.load(database, guild_id)

    try:
        apply_updates(obj, spec.fields, updates)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await spec.save(database, obj)
    collection = SETTINGS_DOMAIN_TO_COLLECTION.get(domain)
    if collection:
        await ws_manager.broadcast_invalidate(collection, guild_id)
    return get_effective_settings(obj, spec.fields)


@router.post("/settings/{domain}/reset")
async def reset_domain_settings(guild_id: int, domain: str, request: Request) -> dict:
    require_guild_access(request, guild_id)
    spec = _get_domain(domain)
    if not spec.reset_sources:
        raise HTTPException(status_code=400, detail="This settings domain does not support reset")

    obj = await spec.load(database, guild_id)
    for source in spec.reset_sources:
        setattr(obj, source, None)

    await spec.save(database, obj)
    collection = SETTINGS_DOMAIN_TO_COLLECTION.get(domain)
    if collection:
        await ws_manager.broadcast_invalidate(collection, guild_id)
    return get_effective_settings(obj, spec.fields)
