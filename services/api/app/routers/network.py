from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.auth.deps import require_guild_access
from app.db import database
from app.settings.domains.network import FIELDS
from app.settings.types import apply_updates, get_effective_settings, to_schema_dicts
from app.ws import manager as ws_manager

router = APIRouter(prefix="/api/guilds/{guild_id}/network", tags=["network"])


async def _resolve(guild_id: int):
    """Returns (network_guild_config, network) or (None, None) if not in a network."""
    ngc = await database.network_guild_config.get(guild_id)
    if ngc is None or not ngc.network_id:
        return None, None
    network = await database.networks.get(ngc.network_id)
    if network is None:
        return ngc, None
    return ngc, network


def _session_user_id(request: Request) -> int:
    user = request.session.get("user")
    if user is None:
        raise HTTPException(status_code=401, detail="Not logged in")
    return int(user["id"])


@router.get("-schema")
async def get_network_schema(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    return to_schema_dicts(FIELDS)


@router.get("")
async def get_network(guild_id: int, request: Request) -> dict:
    require_guild_access(request, guild_id)
    user_id = _session_user_id(request)
    _ngc, network = await _resolve(guild_id)

    if network is None:
        return {"member": False, "network": None, "settings": None, "is_owner": False}

    return {
        "member": True,
        "network": {
            "id": network.id,
            "name": network.name,
            "owner_id": network.owner_id,
            "guild_ids": network.guild_ids,
            "guild_count": len(network.guild_ids),
        },
        "settings": get_effective_settings(network, FIELDS),
        "is_owner": network.owner_id == user_id,
    }


@router.patch("")
async def patch_network(
    guild_id: int,
    request: Request,
    updates: dict[str, bool | int | float | str | None],
) -> dict:
    require_guild_access(request, guild_id)
    user_id = _session_user_id(request)
    _ngc, network = await _resolve(guild_id)

    if network is None:
        raise HTTPException(status_code=404, detail="This server is not part of a network")
    if network.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Only the network owner can change these settings")

    try:
        apply_updates(network, FIELDS, updates)
    except KeyError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await database.networks.save(network)
    await ws_manager.broadcast_invalidate("networks", network.id)
    return get_effective_settings(network, FIELDS)
