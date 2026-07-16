"""Lightweight config loader for the API service.

Reads the same `config.json` the bot uses (repo root), but — unlike
`utils.config.Config` — never prompts interactively and doesn't require
bot-only fields (langfile, token) to be present.
"""

from __future__ import annotations

import json
import pathlib
from functools import lru_cache

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
_CONFIG_PATH = _REPO_ROOT / "config.json"


class ApiConfig:
    def __init__(self, data: dict) -> None:
        self.dbstring: str = _require(data, "dbstring")
        self.bot_token: str = _require(data, "token")
        self.discord_client_id: str = _require(data, "discord_client_id")
        self.discord_client_secret: str = _require(data, "discord_client_secret")
        self.discord_redirect_uri: str = _require(data, "discord_redirect_uri")
        self.session_secret: str = _require(data, "session_secret")
        self.dashboard_frontend_url: str | None = data.get("dashboard_frontend_url") or None

        # Internal bot<->API WebSocket link (instant config-cache invalidation).
        # Optional: when unset, the /internal/ws endpoint rejects all connections.
        self.internal_api_secret: str | None = data.get("internal_api_secret") or None


def _require(data: dict, key: str) -> str:
    value = data.get(key)
    if not value or value == "SET ME!!":
        raise ValueError(
            f"config.json is missing required key '{key}' for services/api. "
            f"See config.sample.json for the full list of dashboard-related keys."
        )
    return value


@lru_cache
def get_config() -> ApiConfig:
    with open(_CONFIG_PATH) as f:
        data = json.load(f)
    return ApiConfig(data)
