# Database wrapper
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import asyncio
import logging
from typing import Any, TypeVar, cast

from pymongo import ASCENDING, AsyncMongoClient
from pymongo.errors import OperationFailure

from utils.cache import Cache

# ── Helpers ───────────────────────────────────────────────────────────────────

def convert_except_none(value: Any, type: type[Any], default: Any = None, error: bool = True) -> Any:
    if value is None:
        return None
    try:
        return type(value)
    except (ValueError, TypeError):
        if error:
            raise ValueError(f'Could not convert {value!r} to {type}')
        return default


def remove_none_values(dictionary: dict) -> dict:
    return {k: v for k, v in dictionary.items() if v is not None}


# ── Schemas ───────────────────────────────────────────────────────────────────

class Schemas:
    class BaseSchema:
        def __init__(self) -> None:
            pass

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.BaseSchema':
            raise NotImplementedError

        def to_dict(self) -> dict:
            raise NotImplementedError

        def __str__(self) -> str:
            d = self.to_dict()
            inner = ', '.join(f'{k}={v}' for k, v in d.items())
            return f'{self.__class__.__name__}({inner})'

        def __repr__(self) -> str:
            return self.__str__()

        def __iter__(self):
            yield from self.to_dict().items()

        def __getitem__(self, key: str) -> Any:
            return getattr(self, key)

    class AutoModSettings(BaseSchema):
        def __init__(self, guild_id: int | None = None, log_channel: int | None = None,
                     whitelist: list[int] | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.log_channel: int | None = convert_except_none(log_channel, int)
            self.whitelist: list[int] | None = convert_except_none(whitelist, list)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.AutoModSettings':
            if data is None:
                return cls()
            guild_id = data.get('guild_id') or data.get('guild')
            return cls(guild_id, data.get('log_channel'), data.get('whitelist'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id, 'log_channel': self.log_channel,
                'whitelist': self.whitelist,
            })

    class Currency(BaseSchema):
        def __init__(self, user_id: str | None = None, wallet: int | None = None,
                     bank: int | None = None, inventory: dict | None = None) -> None:
            self.user_id: str | None = convert_except_none(user_id, str)
            self.wallet: int | None = convert_except_none(wallet, int)
            self.bank: int | None = convert_except_none(bank, int)
            self.inventory: dict | None = inventory

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.Currency':
            # support legacy 'userID' field name
            if data is None:
                return cls()
            user_id = data.get('user_id') or data.get('userID')
            return cls(user_id, data.get('wallet'), data.get('bank'), data.get('inventory'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user_id': self.user_id, 'wallet': self.wallet,
                'bank': self.bank, 'inventory': self.inventory,
            })

    class ScammerList(BaseSchema):
        def __init__(self, user_id: int | None = None, time: int | None = None,
                     reason: str | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.time: int | None = convert_except_none(time, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ScammerList':
            # support legacy 'user' field name
            if data is None:
                return cls()
            user_id = data.get('user_id') or data.get('user')
            return cls(user_id, data.get('time'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({'user_id': self.user_id, 'time': self.time, 'reason': self.reason})

    class ServerBans(BaseSchema):
        def __init__(self, id: int | None = None, name: int | None = None,
                     owner: int | None = None, reason: str | None = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.name: int | None = convert_except_none(name, int)
            self.owner: int | None = convert_except_none(owner, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ServerBans':
            if data is None:
                return cls()
            return cls(data.get('id'), data.get('name'), data.get('owner'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({'id': self.id, 'name': self.name, 'owner': self.owner, 'reason': self.reason})

    class RoleSchema(BaseSchema):
        def __init__(self, id: int | None = None, delay: int | None = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.delay: int | None = convert_except_none(delay, int)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.RoleSchema':
            if data is None:
                return cls()
            return cls(data.get('id'), data.get('delay'))

        def to_dict(self) -> dict:
            return remove_none_values({'id': self.id, 'delay': self.delay})

    class AutoRoleSettings(BaseSchema):
        def __init__(self, guild_id: int | None = None,
                     roles: list | None = None,
                     bots_get_roles: bool | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.roles: list | None = roles
            self.bots_get_roles: bool | None = convert_except_none(bots_get_roles, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.AutoRoleSettings':
            if data is None:
                return cls()
            guild_id = data.get('guild_id') or data.get('guild')
            # support legacy 'BotsGetRoles' field name
            bots_get_roles = data.get('bots_get_roles') if data.get('bots_get_roles') is not None else data.get('BotsGetRoles')
            return cls(guild_id, data.get('roles'), bots_get_roles)

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'roles': self.roles,
                'bots_get_roles': self.bots_get_roles,
            })

    class ExceptionSchema(BaseSchema):
        def __init__(self, user_id: int | None = None, always_report_errors: bool | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.always_report_errors: bool | None = convert_except_none(always_report_errors, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.ExceptionSchema':
            if data is None:
                return cls()
            return cls(data.get('user_id'), data.get('always_report_errors'))

        def to_dict(self) -> dict:
            return remove_none_values({'user_id': self.user_id, 'always_report_errors': self.always_report_errors})

    class UserConfig(BaseSchema):
        def __init__(self, user_id: int | None = None, announce_level: int | None = None,
                     ephemeral_moderation_messages: bool | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.announce_level: int | None = convert_except_none(announce_level, int)
            self.ephemeral_moderation_messages: bool | None = convert_except_none(ephemeral_moderation_messages, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.UserConfig':
            if data is None:
                return cls()
            return cls(data.get('user_id'), data.get('announce_level'), data.get('ephemeral_moderation_messages'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user_id': self.user_id, 'announce_level': self.announce_level,
                'ephemeral_moderation_messages': self.ephemeral_moderation_messages,
            })

    class GuildConfig(BaseSchema):
        def __init__(self, guild_id: int | None = None,
                     ephemeral_moderation_messages: bool | None = None,
                     ephemeral_setting_overpowers_user_setting: bool | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.ephemeral_moderation_messages: bool | None = convert_except_none(ephemeral_moderation_messages, bool)
            self.ephemeral_setting_overpowers_user_setting: bool | None = convert_except_none(
                ephemeral_setting_overpowers_user_setting, bool)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.GuildConfig':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('ephemeral_moderation_messages'),
                       data.get('ephemeral_setting_overpowers_user_setting'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'ephemeral_moderation_messages': self.ephemeral_moderation_messages,
                'ephemeral_setting_overpowers_user_setting': self.ephemeral_setting_overpowers_user_setting,
            })

    class WarnSchema(BaseSchema):
        def __init__(self, user_id: int | None = None, guild_id: int | None = None,
                     warns: list[dict] | None = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.warns: list[dict] | None = warns

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.WarnSchema':
            if data is None:
                return cls()
            return cls(data.get('user_id'), data.get('guild_id'), data.get('warns'))

        def to_dict(self) -> dict:
            return remove_none_values({'user_id': self.user_id, 'guild_id': self.guild_id, 'warns': self.warns})

    class MusicQueue(BaseSchema):
        def __init__(self, guild_id: int | None = None, voice_channel_id: int | None = None,
                     text_channel_id: int | None = None, current: dict | None = None,
                     queue: list | None = None, loop_mode: str | None = None,
                     volume: float | None = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.voice_channel_id: int | None = convert_except_none(voice_channel_id, int)
            self.text_channel_id: int | None = convert_except_none(text_channel_id, int)
            self.current: dict | None = current
            self.queue: list = queue if queue is not None else []
            self.loop_mode: str | None = convert_except_none(loop_mode, str)
            self.volume: float | None = convert_except_none(volume, float)

        @classmethod
        def from_dict(cls, data: dict | None) -> 'Schemas.MusicQueue':
            if data is None:
                return cls()
            return cls(data.get('guild_id'), data.get('voice_channel_id'), data.get('text_channel_id'),
                       data.get('current'), data.get('queue', []), data.get('loop_mode'), data.get('volume'))

        def to_dict(self) -> dict:
            d = remove_none_values({
                'guild_id': self.guild_id, 'voice_channel_id': self.voice_channel_id,
                'text_channel_id': self.text_channel_id, 'current': self.current,
                'loop_mode': self.loop_mode, 'volume': self.volume,
            })
            d['queue'] = self.queue
            return d


T = TypeVar('T', bound=Schemas.BaseSchema)


# ── Collection ────────────────────────────────────────────────────────────────

class Collection[T: Schemas.BaseSchema]:
    """Typed async wrapper around a pymongo collection with an O(1) pk cache.

    All methods accept and return schema objects — raw dicts never leave this class.
    """

    def __init__(self, collection: Any, primary_key: str,
                 schema_class: type[T],
                 cache_ttl: int = 300,
                 legacy_pk: str | None = None) -> None:
        self.collection = collection
        self._pk = primary_key
        self._legacy_pk = legacy_pk
        self._schema: type[T] = schema_class
        self.cache: Cache = Cache(primary_key, ttl=cache_ttl)

    def _from_doc(self, doc: dict) -> T:
        return cast(T, self._schema.from_dict(doc))

    async def get(self, pk_value: Any, **extra_filters: Any) -> T | None:
        """Return the schema for this primary key, or None if not found."""
        query = {self._pk: pk_value, **extra_filters}

        # Only use the cache for simple pk-only lookups
        if not extra_filters:
            cached = self.cache.get_one(query)
            if cached is not None:
                return self._from_doc(cached)

        doc = await self.collection.find_one(query)

        if doc is None and self._legacy_pk and not extra_filters:
            doc = await self.collection.find_one({self._legacy_pk: pk_value})

        if doc is None:
            return None
        if not extra_filters:
            self.cache.add(doc)
        return self._from_doc(doc)

    async def all(self, limit: int = 1000) -> list[T]:
        """Return all documents in the collection as schema objects."""
        cursor = self.collection.find({})
        if limit:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        self.cache.add_many(docs)
        return [self._from_doc(d) for d in docs]

    async def save(self, schema: T) -> None:
        """Upsert by primary key. Migrates legacy field names on first write."""
        doc = schema.to_dict()
        pk_val = doc.get(self._pk)

        existing_id = None
        existing = await self.collection.find_one({self._pk: pk_val})
        if existing is None and self._legacy_pk:
            existing = await self.collection.find_one({self._legacy_pk: pk_val})
        if existing is not None:
            existing_id = existing['_id']

        if existing_id is not None:
            await self.collection.replace_one({'_id': existing_id}, doc)
        else:
            await self.collection.insert_one(doc)

        self.cache.add(doc)

    async def delete(self, pk_value: Any, **extra_filters: Any) -> None:
        """Delete by primary key."""
        query = {self._pk: pk_value, **extra_filters}
        result = await self.collection.delete_one(query)
        if result.deleted_count == 0 and self._legacy_pk and not extra_filters:
            await self.collection.delete_one({self._legacy_pk: pk_value})
        self.cache.remove({self._pk: pk_value})

    async def exists(self, pk_value: Any, **extra_filters: Any) -> bool:
        return await self.get(pk_value, **extra_filters) is not None

    async def count(self, **filters: Any) -> int:
        return await self.collection.count_documents(filters)

    async def query_one(self, filter_dict: dict) -> T | None:
        """Escape hatch for complex queries. Returns a schema object."""
        doc = await self.collection.find_one(filter_dict)
        if doc is None:
            return None
        return self._from_doc(doc)

    async def query_many(self, filter_dict: dict, limit: int = 1000) -> list[T]:
        """Escape hatch for complex queries. Returns a list of schema objects."""
        cursor = self.collection.find(filter_dict)
        if limit:
            cursor = cursor.limit(limit)
        docs = await cursor.to_list(length=limit)
        return [self._from_doc(d) for d in docs]


# ── Database ──────────────────────────────────────────────────────────────────

class Database:
    def __init__(self, dbstring: str) -> None:
        self.dbstring = dbstring
        self.connected = False
        self._cleanup_task: asyncio.Task | None = None

    async def connect(self) -> None:
        if self.connected:
            return

        logging.info('Connecting to database.')
        self.client: AsyncMongoClient = AsyncMongoClient(
            self.dbstring, serverSelectionTimeoutMS=5000)

        try:
            await self.client.server_info()
        except Exception as e:
            logging.critical('Failed to connect to database.')
            raise e

        logging.info('Connected to database.')
        self.connected = True

        db = self.client.data

        self.automodsettings: Collection[Schemas.AutoModSettings] = Collection(
            db.automodsettings, 'guild_id', Schemas.AutoModSettings, legacy_pk='guild')
        self.currency: Collection[Schemas.Currency] = Collection(
            db.currency, 'user_id', Schemas.Currency, legacy_pk='userID')
        self.scammer_list: Collection[Schemas.ScammerList] = Collection(
            db.scammer_list, 'user_id', Schemas.ScammerList, legacy_pk='user')
        self.serverbans: Collection[Schemas.ServerBans] = Collection(
            db.serverbans, 'id', Schemas.ServerBans)
        self.autorolesettings: Collection[Schemas.AutoRoleSettings] = Collection(
            db.autorolesettings, 'guild_id', Schemas.AutoRoleSettings, legacy_pk='guild')
        self.exceptions: Collection[Schemas.ExceptionSchema] = Collection(
            db.exceptions, 'user_id', Schemas.ExceptionSchema)
        self.user_config: Collection[Schemas.UserConfig] = Collection(
            db.user_config, 'user_id', Schemas.UserConfig)
        self.guild_config: Collection[Schemas.GuildConfig] = Collection(
            db.guild_config, 'guild_id', Schemas.GuildConfig)
        self.warnings: Collection[Schemas.WarnSchema] = Collection(
            db.warnings, 'user_id', Schemas.WarnSchema)
        self.music_queues: Collection[Schemas.MusicQueue] = Collection(
            db.music_queues, 'guild_id', Schemas.MusicQueue)

        self.collections: list[Collection] = [
            self.automodsettings,
            self.currency, self.scammer_list, self.serverbans,
            self.autorolesettings, self.exceptions, self.user_config,
            self.guild_config, self.warnings, self.music_queues,
        ]

        await self._ensure_indexes(db)
        self._cleanup_task = asyncio.create_task(self._cache_cleanup_loop())

    @staticmethod
    async def _create_index(collection: Any, keys: Any, **options: Any) -> None:
        """Create an index, recreating it if a prior run left an incompatible
        definition (e.g. non-sparse before legacy documents were accounted for)."""
        key_spec = [(keys, ASCENDING)] if isinstance(keys, str) else list(keys)
        try:
            await collection.create_index(keys, **options)
        except OperationFailure as e:
            if e.code in (85, 86):  # IndexOptionsConflict / IndexKeySpecsConflict
                async for index in await collection.list_indexes():
                    if list(index["key"].items()) == key_spec:
                        await collection.drop_index(index["name"])
                        break
                await collection.create_index(keys, **options)
            else:
                raise

    async def _ensure_indexes(self, db: Any) -> None:
        # sparse=True so legacy documents that still use the old field names
        # (and therefore lack the new primary key field) don't collide on a
        # shared `null` value when the unique index is built.
        await self._create_index(db.automodsettings, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.autorolesettings, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.guild_config, 'guild_id', unique=True, sparse=True)
        await self._create_index(db.currency, 'user_id', unique=True, sparse=True)
        await self._create_index(db.scammer_list, 'user_id', unique=True, sparse=True)
        await self._create_index(db.user_config, 'user_id', unique=True, sparse=True)
        await self._create_index(db.exceptions, 'user_id', unique=True, sparse=True)
        await self._create_index(db.warnings, [('user_id', ASCENDING), ('guild_id', ASCENDING)])
        await self._create_index(db.music_queues, 'guild_id', unique=True, sparse=True)

    async def _cache_cleanup_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            for col in self.collections:
                col.cache.cleanup()
