from __future__ import annotations

from utils.database import Schemas

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("guild_config", Schemas.GuildConfig)

FIELDS: list[FieldDescriptor] = [
    FieldDescriptor(
        "ephemeral_moderation_messages",
        "bool",
        "Ephemeral moderation messages",
        "Whether moderation command responses are only visible to the moderator by default.",
        default=False,
    ),
    FieldDescriptor(
        "ephemeral_setting_overpowers_user_setting",
        "bool",
        "Guild setting overrides user preference",
        "If enabled, this server's ephemeral setting always wins over an individual moderator's own preference.",
        default=False,
    ),
    FieldDescriptor(
        "invite_log_channel_id",
        "channel",
        "Invite log channel",
        "Channel that receives invite-tracking join/leave logs.",
        default=None,
    ),
]

GUILD_CONFIG = DomainSpec(
    key="guild_config",
    label="General",
    fields=FIELDS,
    load=_load,
    save=_save,
    description="General server-wide bot behavior.",
)
