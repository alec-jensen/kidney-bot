"""Network settings are keyed by network id (not guild_id) and only editable by
the network's owner — this domain is intentionally NOT registered in the
generic DOMAINS registry; app/routers/network.py handles resolution +
ownership checks directly, reusing these field descriptors for the scalar
get/patch logic.
"""

from __future__ import annotations

from app.settings.types import FieldDescriptor

FIELDS: list[FieldDescriptor] = [
    FieldDescriptor(
        "propagate_bans",
        "bool",
        "Propagate bans",
        "Automatically propagate bans to every server in this network.",
        default=True,
    ),
    FieldDescriptor(
        "propagate_kicks",
        "bool",
        "Propagate kicks",
        "Automatically propagate kicks to every server in this network.",
        default=False,
    ),
    FieldDescriptor(
        "propagate_mutes",
        "bool",
        "Propagate mutes",
        "Automatically propagate timeouts to every server in this network.",
        default=False,
    ),
    FieldDescriptor(
        "share_heuristics",
        "bool",
        "Share heuristics reputation",
        "Share cross-server heuristics reputation (flags/trust) within the network.",
        default=True,
    ),
    FieldDescriptor(
        "sync_raid_alerts",
        "bool",
        "Sync raid alerts",
        "Broadcast raid alerts (join clusters) to every server in the network.",
        default=True,
    ),
]
