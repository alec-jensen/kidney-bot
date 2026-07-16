from __future__ import annotations

from utils.database import Schemas

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("automodsettings", Schemas.AutoModSettings)

FIELDS: list[FieldDescriptor] = [
    FieldDescriptor("log_channel", "channel", "Log channel", "Channel automod sends its logs to.", default=None),
]

AUTOMOD = DomainSpec(
    key="automod",
    label="Automod",
    fields=FIELDS,
    load=_load,
    save=_save,
    description="Automod logging. Manage the user/channel whitelist from the whitelist list editor on this page.",
)
