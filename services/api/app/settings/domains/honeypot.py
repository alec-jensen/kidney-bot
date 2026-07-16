from __future__ import annotations

from utils.database import Schemas

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("honeypot_config", Schemas.HoneypotConfig)

# `channel_id` is deliberately excluded: setting it requires actually posting the
# verify message with its persistent button, which is a side-effecting action —
# see POST /api/guilds/{id}/honeypot/enable instead of a plain field write.
FIELDS: list[FieldDescriptor] = [
    FieldDescriptor("enabled", "bool", "Enabled", "Whether the honeypot channel is currently active.", default=False),
    FieldDescriptor(
        "mode",
        "enum",
        "Mode",
        "Visibility: hide the channel once verified. Lockdown: assign a pending role on join that's lifted on verify.",
        default="visibility",
        choices=["visibility", "lockdown"],
    ),
    FieldDescriptor(
        "message_action",
        "enum",
        "Action on message",
        "What happens to a member who sends a message in the honeypot channel.",
        default="kick",
        choices=["kick", "ban", "mute"],
    ),
    FieldDescriptor(
        "verify_role_id",
        "role",
        "Verify role",
        "Visibility mode: role added when a member verifies (should have a DENY overwrite on the honeypot channel).",
        default=None,
        depends_on={"field": "mode", "value": "visibility"},
    ),
    FieldDescriptor(
        "pending_role_id",
        "role",
        "Pending role",
        "Lockdown mode: role assigned on join, restricting access until verified.",
        default=None,
        depends_on={"field": "mode", "value": "lockdown"},
    ),
    FieldDescriptor(
        "alert_channel_id",
        "channel",
        "Alert channel",
        "Channel notified when someone triggers the honeypot.",
        default=None,
    ),
]

HONEYPOT = DomainSpec(
    key="honeypot",
    label="Honeypot",
    fields=FIELDS,
    load=_load,
    save=_save,
    description="Bot-catching honeypot channel. Use the 'Enable in channel' action on this page "
    "to pick (or change) which channel hosts the verification message.",
)
