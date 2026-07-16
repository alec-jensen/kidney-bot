from __future__ import annotations

from utils.database import Schemas

from app.settings.types import DomainSpec, FieldDescriptor, simple_domain

_load, _save = simple_domain("autorolesettings", Schemas.AutoRoleSettings)

FIELDS: list[FieldDescriptor] = [
    FieldDescriptor(
        "bots_get_roles",
        "bool",
        "Bots get roles",
        "Whether bot accounts also receive auto-roles on join.",
        default=False,
    ),
]

AUTOROLE = DomainSpec(
    key="autorole",
    label="Auto role",
    fields=FIELDS,
    load=_load,
    save=_save,
    description="Roles automatically given to new members. Manage the role list (with optional "
    "per-role delay) from the roles list editor on this page.",
)
