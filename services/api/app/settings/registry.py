"""Aggregates every generic (guild_id-keyed, non-owner-gated) settings domain.

`network` is deliberately excluded — see `app/settings/domains/network.py` and
`app/routers/network.py` for why it needs bespoke resolution + ownership
checks instead of going through this generic get/patch path.
"""

from __future__ import annotations

from app.settings.domains.automod import AUTOMOD
from app.settings.domains.autorole import AUTOROLE
from app.settings.domains.guild_config import GUILD_CONFIG
from app.settings.domains.heuristics import HEURISTICS_CORE, HEURISTICS_THRESHOLDS, HEURISTICS_WEIGHTS
from app.settings.domains.honeypot import HONEYPOT
from app.settings.domains.moderation import MODERATION
from app.settings.types import DomainSpec

DOMAINS: dict[str, DomainSpec] = {
    d.key: d
    for d in [
        GUILD_CONFIG,
        HEURISTICS_CORE,
        HEURISTICS_WEIGHTS,
        HEURISTICS_THRESHOLDS,
        AUTOMOD,
        AUTOROLE,
        MODERATION,
        HONEYPOT,
    ]
}
