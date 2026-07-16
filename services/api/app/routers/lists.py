"""CRUD endpoints for the settings fields that are variable-length collections
rather than scalars: automod's whitelist, autorole's role+delay list,
moderation's escalation rules, and the network watchlist. Each gets its own
small set of routes instead of forcing a one-size-fits-all list abstraction
onto four genuinely different item shapes.
"""

from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from utils.database import Schemas
from utils.mod_insight import DEFAULT_RULES

from app.auth.deps import require_guild_access
from app.db import database
from app.ws import manager as ws_manager

router = APIRouter(prefix="/api/guilds/{guild_id}", tags=["lists"])

SUGGESTION_ACTIONS = ["warn", "tempmute", "mute", "kick", "ban"]
CONDITION_ACTION_TYPES = list(Schemas.ModLogEntry.ACTION_TYPES)


# ── Automod whitelist (list[int]) ──────────────────────────────────────────────


class WhitelistItem(BaseModel):
    id: str


@router.get("/automod/whitelist")
async def get_whitelist(guild_id: int, request: Request) -> list[str]:
    require_guild_access(request, guild_id)
    doc = await database.automodsettings.get(guild_id)
    return [str(i) for i in (doc.whitelist or [])] if doc else []


@router.post("/automod/whitelist")
async def add_whitelist_item(guild_id: int, request: Request, item: WhitelistItem) -> list[str]:
    require_guild_access(request, guild_id)
    doc = await database.automodsettings.get(guild_id) or Schemas.AutoModSettings(guild_id=guild_id)
    whitelist = doc.whitelist or []
    item_id = int(item.id)
    if item_id not in whitelist:
        whitelist.append(item_id)
    doc.whitelist = whitelist
    await database.automodsettings.save(doc)
    await ws_manager.broadcast_invalidate("automodsettings", guild_id)
    return [str(i) for i in whitelist]


@router.delete("/automod/whitelist/{item_id}")
async def remove_whitelist_item(guild_id: int, item_id: int, request: Request) -> list[str]:
    require_guild_access(request, guild_id)
    doc = await database.automodsettings.get(guild_id)
    whitelist = list(doc.whitelist or []) if doc else []
    whitelist = [i for i in whitelist if i != item_id]
    if doc is None:
        doc = Schemas.AutoModSettings(guild_id=guild_id)
    doc.whitelist = whitelist
    await database.automodsettings.save(doc)
    await ws_manager.broadcast_invalidate("automodsettings", guild_id)
    return [str(i) for i in whitelist]


# ── Autorole roles (list[{id, delay}]) ─────────────────────────────────────────


class RoleItem(BaseModel):
    id: str
    delay: int = 0


@router.get("/autorole/roles")
async def get_autorole_roles(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    doc = await database.autorolesettings.get(guild_id)
    roles = (doc.roles or []) if doc else []
    return [{"id": str(r["id"]), "delay": r.get("delay", 0)} for r in roles]


@router.post("/autorole/roles")
async def upsert_autorole_role(guild_id: int, request: Request, item: RoleItem) -> list[dict]:
    require_guild_access(request, guild_id)
    doc = await database.autorolesettings.get(guild_id) or Schemas.AutoRoleSettings(guild_id=guild_id, roles=[])
    roles = doc.roles or []
    role_id = int(item.id)
    existing = next((r for r in roles if r["id"] == role_id), None)
    if existing is not None:
        existing["delay"] = item.delay
    else:
        roles.append({"id": role_id, "delay": item.delay})
    doc.roles = roles
    await database.autorolesettings.save(doc)
    await ws_manager.broadcast_invalidate("autorolesettings", guild_id)
    return [{"id": str(r["id"]), "delay": r.get("delay", 0)} for r in roles]


@router.delete("/autorole/roles/{role_id}")
async def remove_autorole_role(guild_id: int, role_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    doc = await database.autorolesettings.get(guild_id)
    roles = (doc.roles or []) if doc else []
    roles = [r for r in roles if r["id"] != role_id]
    if doc is None:
        doc = Schemas.AutoRoleSettings(guild_id=guild_id)
    doc.roles = roles
    await database.autorolesettings.save(doc)
    await ws_manager.broadcast_invalidate("autorolesettings", guild_id)
    return [{"id": str(r["id"]), "delay": r.get("delay", 0)} for r in roles]


# ── Moderation escalation rules ─────────────────────────────────────────────────


class SuggestionItem(BaseModel):
    action_type: str
    duration: str | None = None


class EscalationRuleItem(BaseModel):
    action_types: list[str]
    min_count: int
    window_days: int
    suggestions: list[SuggestionItem]


def _validate_rule(rule: EscalationRuleItem) -> None:
    bad_conditions = [a for a in rule.action_types if a not in CONDITION_ACTION_TYPES]
    if bad_conditions:
        raise HTTPException(status_code=400, detail=f"Invalid action_types: {bad_conditions}")
    bad_suggestions = [s.action_type for s in rule.suggestions if s.action_type not in SUGGESTION_ACTIONS]
    if bad_suggestions:
        raise HTTPException(status_code=400, detail=f"Invalid suggestion action_type: {bad_suggestions}")


@router.get("/moderation/escalation-rules")
async def get_escalation_rules(guild_id: int, request: Request) -> dict:
    require_guild_access(request, guild_id)
    doc = await database.mod_config.get(guild_id)
    if doc is None or doc.escalation_rules is None:
        return {"using_defaults": True, "rules": [r.to_dict() for r in DEFAULT_RULES]}
    return {"using_defaults": False, "rules": doc.escalation_rules}


@router.post("/moderation/escalation-rules")
async def add_escalation_rule(guild_id: int, request: Request, rule: EscalationRuleItem) -> dict:
    require_guild_access(request, guild_id)
    _validate_rule(rule)
    doc = await database.mod_config.get(guild_id) or Schemas.ModConfig(guild_id=guild_id)
    rules = doc.escalation_rules if doc.escalation_rules is not None else [r.to_dict() for r in DEFAULT_RULES]
    rules.append(
        {
            "id": str(uuid4()),
            "conditions": {
                "action_types": rule.action_types,
                "min_count": rule.min_count,
                "window_days": rule.window_days,
            },
            "suggestions": [
                {"action_type": s.action_type, **({"duration": s.duration} if s.duration else {})}
                for s in rule.suggestions
            ],
        }
    )
    doc.escalation_rules = rules
    await database.mod_config.save(doc)
    await ws_manager.broadcast_invalidate("mod_config", guild_id)
    return {"using_defaults": False, "rules": rules}


@router.delete("/moderation/escalation-rules/{rule_id}")
async def remove_escalation_rule(guild_id: int, rule_id: str, request: Request) -> dict:
    require_guild_access(request, guild_id)
    doc = await database.mod_config.get(guild_id)
    rules = doc.escalation_rules if (doc and doc.escalation_rules is not None) else [r.to_dict() for r in DEFAULT_RULES]
    rules = [r for r in rules if r.get("id") != rule_id]
    if doc is None:
        doc = Schemas.ModConfig(guild_id=guild_id)
    doc.escalation_rules = rules
    await database.mod_config.save(doc)
    await ws_manager.broadcast_invalidate("mod_config", guild_id)
    return {"using_defaults": False, "rules": rules}


@router.post("/moderation/escalation-rules/reset")
async def reset_escalation_rules(guild_id: int, request: Request) -> dict:
    require_guild_access(request, guild_id)
    doc = await database.mod_config.get(guild_id) or Schemas.ModConfig(guild_id=guild_id)
    doc.escalation_rules = None
    await database.mod_config.save(doc)
    await ws_manager.broadcast_invalidate("mod_config", guild_id)
    return {"using_defaults": True, "rules": [r.to_dict() for r in DEFAULT_RULES]}


# ── Network watchlist (list[{user_id, reason, added_by, added_at}]) ───────────


class WatchlistItem(BaseModel):
    user_id: str
    reason: str


@router.get("/network/watchlist")
async def get_watchlist(guild_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    ngc = await database.network_guild_config.get(guild_id)
    if ngc is None or not ngc.network_id:
        return []
    network = await database.networks.get(ngc.network_id)
    if network is None:
        return []
    return [{**entry, "user_id": str(entry["user_id"])} for entry in network.watchlist]


@router.post("/network/watchlist")
async def add_watchlist_item(guild_id: int, request: Request, item: WatchlistItem) -> list[dict]:
    require_guild_access(request, guild_id)
    user = request.session.get("user")
    ngc = await database.network_guild_config.get(guild_id)
    if ngc is None or not ngc.network_id:
        raise HTTPException(status_code=404, detail="This server is not part of a network")
    network = await database.networks.get(ngc.network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="This server is not part of a network")

    user_id = int(item.user_id)
    watchlist = [e for e in network.watchlist if e.get("user_id") != user_id]
    watchlist.append(
        {
            "user_id": user_id,
            "reason": item.reason,
            "added_by": int(user["id"]) if user else None,
            "added_at": int(time.time()),
        }
    )
    network.watchlist = watchlist
    await database.networks.save(network)
    await ws_manager.broadcast_invalidate("networks", network.id)
    return [{**e, "user_id": str(e["user_id"])} for e in watchlist]


@router.delete("/network/watchlist/{user_id}")
async def remove_watchlist_item(guild_id: int, user_id: int, request: Request) -> list[dict]:
    require_guild_access(request, guild_id)
    ngc = await database.network_guild_config.get(guild_id)
    if ngc is None or not ngc.network_id:
        raise HTTPException(status_code=404, detail="This server is not part of a network")
    network = await database.networks.get(ngc.network_id)
    if network is None:
        raise HTTPException(status_code=404, detail="This server is not part of a network")

    network.watchlist = [e for e in network.watchlist if e.get("user_id") != user_id]
    await database.networks.save(network)
    await ws_manager.broadcast_invalidate("networks", network.id)
    return [{**e, "user_id": str(e["user_id"])} for e in network.watchlist]
