from __future__ import annotations

from utils.database import Schemas

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("mod_config", Schemas.ModConfig)

FIELDS: list[FieldDescriptor] = [
    FieldDescriptor(
        "log_channel_id",
        "channel",
        "Moderation log channel",
        "Channel that receives warn/mute/kick/ban logs.",
        default=None,
    ),
    FieldDescriptor(
        "require_reason",
        "bool",
        "Require reasons",
        "Require moderators to provide a reason for warns, mutes, kicks, and bans.",
        default=False,
    ),
]

MODERATION = DomainSpec(
    key="moderation",
    label="Moderation",
    fields=FIELDS,
    load=_load,
    save=_save,
    description="Moderation log channel. Escalation rules (auto-suggested actions after repeat "
    "offenses) are managed from the escalation rules list editor on this page.",
)
