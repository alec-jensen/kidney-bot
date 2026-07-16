from __future__ import annotations

from utils.database import Database

from app.config import get_config

database = Database(get_config().dbstring)
