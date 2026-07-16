"""Public command documentation endpoint — powers the web docs page.

Reuses `utils.command_catalog` from the bot's own source tree directly so the
in-Discord /help command and the public docs page can never drift apart.
No auth: this data is not guild-specific or sensitive.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from utils.command_catalog import COMMAND_CATALOG

router = APIRouter(prefix="/api/docs", tags=["docs"])


def _serialize_param(param: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": param.get("name"),
        "type": param.get("type"),
        "required": param.get("required"),
        # the catalog's internal shape uses "desc"; the public contract uses
        # "description" — translate here rather than renaming the source key.
        "description": param.get("desc"),
    }


def _serialize_command(cmd: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": cmd.get("name"),
        "usage": cmd.get("usage"),
        "brief": cmd.get("brief"),
        "description": cmd.get("description"),
        "params": [_serialize_param(p) for p in cmd.get("params", [])],
        "perm": cmd.get("perm"),
        "examples": cmd.get("examples", []),
    }


def _serialize_category(cat: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": cat.get("name"),
        "description": cat.get("description"),
        "commands": [_serialize_command(c) for c in cat.get("commands", [])],
    }


@router.get("/commands")
async def get_commands() -> dict[str, Any]:
    return {"categories": [_serialize_category(cat) for cat in COMMAND_CATALOG]}
