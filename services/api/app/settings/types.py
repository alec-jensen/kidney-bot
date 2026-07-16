"""Generic settings-descriptor engine.

One `FieldDescriptor` shape drives the schema endpoint (so the frontend can
render a generic form) and the get/patch endpoints for any config object.
A field either lives directly on the schema object (`source="top_level"`) or
inside a dict-valued field on that object (`source="<dict_field_name>"`,
e.g. `"weight_overrides"`) — the same pattern `GuildHeuristicsConfig` already
used for `action_overrides`, generalized to any override dict and any schema.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

FieldType = Literal["bool", "int", "float", "str", "channel", "role", "enum"]


@dataclass(frozen=True)
class FieldDescriptor:
    name: str
    type: FieldType
    label: str
    help: str
    source: str = "top_level"
    default: Any = None
    min: float | None = None
    max: float | None = None
    choices: list[str] | None = None
    # Sub-section label for grouping long field lists in the UI (e.g. heuristics
    # weights get grouped by "Account age", "Username", etc). None = ungrouped.
    group: str | None = None
    # Conditional visibility: only show this field in the UI when the named
    # sibling field's current value equals `value`, e.g.
    # {"field": "auto_delete_on_ban", "value": True}. None = always shown.
    depends_on: dict | None = None


def to_schema_dicts(fields: list[FieldDescriptor]) -> list[dict[str, Any]]:
    return [
        {
            "name": f.name,
            "type": f.type,
            "label": f.label,
            "help": f.help,
            "source": f.source,
            "default": f.default,
            "min": f.min,
            "max": f.max,
            "choices": f.choices,
            "group": f.group,
            "depends_on": f.depends_on,
        }
        for f in fields
    ]


# Discord snowflakes are 64-bit integers that exceed JavaScript's safe integer
# range (2^53) — transmitted as JSON numbers they get silently rounded on the
# frontend. Fields of these types cross the API boundary as strings instead.
_ID_TYPES = {"channel", "role"}


def _to_wire(f: FieldDescriptor, value: Any) -> Any:
    if value is not None and f.type in _ID_TYPES:
        return str(value)
    return value


def _from_wire(f: FieldDescriptor, value: Any) -> Any:
    if value is not None and f.type in _ID_TYPES:
        return int(value)
    return value


def get_effective_settings(obj: Any, fields: list[FieldDescriptor]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for f in fields:
        if f.source == "top_level":
            value = getattr(obj, f.name)
            value = value if value is not None else f.default
        else:
            overrides = getattr(obj, f.source) or {}
            value = overrides.get(f.name, f.default)
        result[f.name] = _to_wire(f, value)
    return result


def apply_updates(obj: Any, fields: list[FieldDescriptor], updates: dict[str, Any]) -> None:
    fields_by_name = {f.name: f for f in fields}
    dict_field_updates: dict[str, dict[str, Any]] = {}
    for name, raw_value in updates.items():
        descriptor = fields_by_name.get(name)
        if descriptor is None:
            raise KeyError(f"Unknown settings field: {name}")
        value = _from_wire(descriptor, raw_value)
        if descriptor.source == "top_level":
            setattr(obj, name, value)
        else:
            bucket = dict_field_updates.setdefault(descriptor.source, dict(getattr(obj, descriptor.source) or {}))
            bucket[name] = value
    for source_field, new_dict in dict_field_updates.items():
        setattr(obj, source_field, new_dict or None)


Loader = Callable[[Any, int], Awaitable[Any]]
Saver = Callable[[Any, Any], Awaitable[None]]


@dataclass
class DomainSpec:
    key: str
    label: str
    description: str
    fields: list[FieldDescriptor]
    load: Loader
    save: Saver
    # Override-dict attribute names (on the schema object) that a reset clears,
    # e.g. ["weight_overrides"]. None/empty means this domain doesn't support reset.
    reset_sources: list[str] | None = None


def simple_domain(collection_attr: str, schema_cls: type) -> tuple[Loader, Saver]:
    """Load/save pair for the common case: a Collection keyed directly by guild_id."""

    async def load(database: Any, guild_id: int) -> Any:
        collection = getattr(database, collection_attr)
        obj = await collection.get(guild_id)
        return obj if obj is not None else schema_cls(guild_id=guild_id)

    async def save(database: Any, obj: Any) -> None:
        collection = getattr(database, collection_attr)
        await collection.save(obj)

    return load, save
