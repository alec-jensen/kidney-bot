# Database wrapper for intellisense
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import logging
from typing import Any
import motor.motor_asyncio
import asyncio


def convert_except_none(value, type):
    if value is None:
        return None

    return type(value)


def remove_none_values(dictionary: dict) -> dict:
    return {key: value for key, value in dictionary.items() if value is not None}


class Schemas:
    class BaseSchema:
        def __init__(self) -> None:
            pass

        @classmethod
        def from_dict(cls, data: dict) -> None:
            raise NotImplementedError(
                'This method must be implemented in a subclass.')

        def to_dict(self) -> dict:
            raise NotImplementedError(
                'This method must be implemented in a subclass.')

        def __str__(self) -> str:
            string_repr = self.__class__.__name__ + '('
            items = []
            for key, value in self.to_dict().items():
                items.append(f'{key}={value}')

            string_repr = string_repr + ', '.join(items)
            string_repr = string_repr + ')'
            return string_repr

        def __repr__(self) -> str:
            return self.__str__()

        def __iter__(self):
            for key, value in self.to_dict().items():
                yield key, value

        def __getitem__(self, key: str) -> Any:
            return getattr(self, key)

    class ActiveGuardSettings(BaseSchema):
        def __init__(self, guild_id: int = None, block_known_spammers: bool = None) -> None:
            self.guild_id: int | None = convert_except_none(guild_id, int)
            self.block_known_spammers: bool | None = convert_except_none(
                block_known_spammers, bool)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.ActiveGuardSettings':
            if data is None:
                return cls()

            return cls(data.get("guild_id"), data.get("block_known_spammers"))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'block_known_spammers': self.block_known_spammers
            })

    class AiDetection(BaseSchema):
        def __init__(self, guild: int = None, channel_id: int = None, enabled: bool = None, TOXICITY: int = None, SEVERE_TOXICITY: int = None, IDENTITY_ATTACK: int = None, INSULT: int = None, PROFANITY: int = None, THREAT: int = None, FLIRTATION: int = None, OBSCENE: int = None, SPAM: int = None) -> None:
            self.guild_id: int | None = convert_except_none(guild, int)
            self.channel_id: int | None = convert_except_none(channel_id, int)
            self.enabled: bool | None = convert_except_none(enabled, bool)
            self.TOXICITY: int | None = convert_except_none(TOXICITY, int)
            self.SEVERE_TOXICITY: int | None = convert_except_none(
                SEVERE_TOXICITY, int)
            self.IDENTITY_ATTACK: int | None = convert_except_none(
                IDENTITY_ATTACK, int)
            self.INSULT: int | None = convert_except_none(INSULT, int)
            self.PROFANITY: int | None = convert_except_none(PROFANITY, int)
            self.THREAT: int | None = convert_except_none(THREAT, int)
            self.FLIRTATION: int | None = convert_except_none(FLIRTATION, int)
            self.OBSCENE: int | None = convert_except_none(OBSCENE, int)
            self.SPAM: int | None = convert_except_none(SPAM, int)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.AiDetection':
            if data is None:
                return cls()

            return cls(data.get('guild_id'), data.get('channel_id'), data.get('enabled'),
                       data.get('TOXICITY'), data.get(
                           'SEVERE_TOXICITY'), data.get('IDENTITY_ATTACK'),
                       data.get('INSULT'), data.get(
                           'PROFANITY'), data.get('THREAT'),
                       data.get('FLIRTATION'), data.get('OBSCENE'), data.get('SPAM'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild_id': self.guild_id,
                'channel_id': self.channel_id,
                'enabled': self.enabled,
                'TOXICITY': self.TOXICITY,
                'SEVERE_TOXICITY': self.SEVERE_TOXICITY,
                'IDENTITY_ATTACK': self.IDENTITY_ATTACK,
                'INSULT': self.INSULT,
                'PROFANITY': self.PROFANITY,
                'THREAT': self.THREAT,
                'FLIRTATION': self.FLIRTATION,
                'OBSCENE': self.OBSCENE,
                'SPAM': self.SPAM
            })

    class AutoModSettings(BaseSchema):
        def __init__(self, guild: int = None, log_channel: int = None) -> None:
            self.guild: int | None = convert_except_none(guild, int)
            self.log_channel: int | None = convert_except_none(
                log_channel, int)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.AutoModSettings':
            if data is None:
                return cls()

            return cls(data.get('guild'), data.get('log_channel'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild': self.guild,
                'log_channel': self.log_channel
            })

    # For whatever reason, all of these are strings
    class Currency(BaseSchema):
        def __init__(self, userID: str = None, wallet: str = None, bank: str = None, inventory: list = None) -> None:
            self.userID: str | None = convert_except_none(userID, str)
            self.wallet: str | None = convert_except_none(wallet, str)
            self.bank: str | None = convert_except_none(bank, str)
            self.inventory: list | None = inventory

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.Currency':
            if data is None:
                return cls()

            return cls(data.get('userID'), data.get('wallet'), data.get('bank'), data.get('inventory'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'userID': self.userID,
                'wallet': self.wallet,
                'bank': self.bank,
                'inventory': self.inventory
            })

    class Reports(BaseSchema):
        def __init__(self, report_id: str = None, reporter: int = None, time_reported: float = None, reported_user: int = None, reported_user_name: str = None, reason: str = None, attached_message: str = None, attached_message_attachments: list = None, report_status: str = None, handled_by: int = None) -> None:
            self.report_id: str | None = convert_except_none(report_id, str)
            self.reporter: int | None = convert_except_none(reporter, int)
            self.time_reported: float | None = convert_except_none(
                time_reported, float)
            self.reported_user: int | None = convert_except_none(
                reported_user, int)
            self.reported_user_name: str | None = convert_except_none(
                reported_user_name, str)
            self.reason: str | None = convert_except_none(reason, str)
            self.attached_message: str | None = convert_except_none(
                attached_message, str)
            self.attached_message_attachments: list | None = attached_message_attachments
            self.report_status: str | None = convert_except_none(
                report_status, str)
            self.handled_by: int | None = convert_except_none(handled_by, int)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.Reports':
            if data is None:
                return cls()

            return cls(data.get('report_id'), data.get('reporter'), data.get('time_reported'), data.get('reported_user'), data.get('reported_user_name'), data.get('reason'), data.get('attached_message'), data.get('attached_message_attachments'), data.get('report_status'), data.get('handled_by'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'report_id': self.report_id,
                'reporter': self.reporter,
                'time_reported': self.time_reported,
                'reported_user': self.reported_user,
                'reported_user_name': self.reported_user_name,
                'reason': self.reason,
                'attached_message': self.attached_message,
                'attached_message_attachments': self.attached_message_attachments,
                'report_status': self.report_status,
                'handled_by': self.handled_by
            })

    class ScammerList(BaseSchema):
        def __init__(self, user: int = None, time: int = None, reason: str = None) -> None:
            self.user: int | None = convert_except_none(user, int)
            self.time: int | None = convert_except_none(time, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.ScammerList':
            if data is None:
                return cls()

            return cls(data.get('user'), data.get('time'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user': self.user,
                'time': self.time,
                'reason': self.reason
            })

    class ServerBans(BaseSchema):
        def __init__(self, id: int = None, name: int = None, owner: int = None, reason: str = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.name: int | None = convert_except_none(name, int)
            self.owner: int | None = convert_except_none(owner, int)
            self.reason: str | None = convert_except_none(reason, str)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.ServerBans':
            if data is None:
                return cls()

            return cls(data.get('id'), data.get('name'), data.get('owner'), data.get('reason'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'id': self.id,
                'name': self.name,
                'owner': self.owner,
                'reason': self.reason
            })

    class RoleSchema(BaseSchema):
        def __init__(self, id: int = None, delay: int = None) -> None:
            self.id: int | None = convert_except_none(id, int)
            self.delay: int | None = convert_except_none(delay, int)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.RoleSchema':
            if data is None:
                return cls()

            return cls(data.get('id'), data.get('delay'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'id': self.id,
                'delay': self.delay
            })

    class AutoRoleSettings(BaseSchema):
        def __init__(self, guild: int = None, roles: list['Schemas.RoleSchema'] = None, BotsGetRoles: bool = None) -> None:
            self.guild: int | None = convert_except_none(guild, int)
            self.roles: list['Schemas.RoleSchema'] | None = roles
            self.BotsGetRoles: bool | None = convert_except_none(
                BotsGetRoles, bool)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.AutoRoleSettings':
            if data is None:
                return cls()

            return cls(data.get('guild'), data.get('roles'), data.get('BotsGetRoles'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'guild': self.guild,
                'roles': self.roles,
                'BotsGetRoles': self.BotsGetRoles
            })

    class ExceptionSchema(BaseSchema):
        def __init__(self, user_id: int = None, always_report_errors: bool = None) -> None:
            self.user_id: int | None = convert_except_none(user_id, int)
            self.always_report_errors: bool | None = convert_except_none(
                always_report_errors, bool)

        @classmethod
        def from_dict(cls, data: dict) -> 'Schemas.ExceptionSchema':
            if data is None:
                return cls()

            return cls(data.get('user_id'), data.get('always_report_errors'))

        def to_dict(self) -> dict:
            return remove_none_values({
                'user_id': self.user_id,
                'always_report_errors': self.always_report_errors
            })


class Collection:
    """Wrapper for motor.motor_asyncio.AsyncIOMotorCollection. If a schema is provided, all queries will be converted to the schema."""

    def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection, schema: Schemas.BaseSchema = None) -> None:
        self.collection: motor.motor_asyncio.AsyncIOMotorCollection = collection
        self.schema: Schemas.BaseSchema = schema

    """Find one document in the collection. If a schema is provided, it will be converted to the schema."""
    async def find_one(self, query: Schemas.BaseSchema | dict, schema: Schemas.BaseSchema = None) -> dict | Schemas.BaseSchema | None:
        if isinstance(query, Schemas.BaseSchema):
            query = query.to_dict()

        document = await self.collection.find_one(query)
        if schema is None:
            schema = self.schema

        if document is None:
            return None

        return document if schema is None else schema.from_dict(document)

    """Find all documents in the collection. If a schema is provided, it will be converted to the schema."""
    async def find(self, query: Schemas.BaseSchema | dict, schema: Schemas.BaseSchema | dict = None) -> list[dict] | list[Schemas.BaseSchema]:
        if isinstance(query, Schemas.BaseSchema):
            query = query.to_dict()

        documents = await self.collection.find(query)
        if self.schema is None:
            return documents

        return [self.schema.from_dict(document) for document in documents]

    """Update one document in the collection."""
    async def update_one(self, query: dict, update: dict) -> None:
        await self.collection.update_one(query, update)

    """Delete one document in the collection."""
    async def delete_one(self, query: dict | Schemas.BaseSchema) -> None:
        if isinstance(query, Schemas.BaseSchema):
            query = query.to_dict()

        await self.collection.delete_one(query)

    """Insert one document in the collection."""
    async def insert_one(self, document: dict | Schemas.BaseSchema) -> None:
        if isinstance(document, Schemas.BaseSchema):
            document = document.to_dict()

        await self.collection.insert_one(document)

    """Count the number of documents in the collection."""
    async def count_documents(self, query: dict | Schemas.BaseSchema) -> int:
        if isinstance(query, Schemas.BaseSchema):
            query = query.to_dict()

        return await self.collection.count_documents(query)


class Database:
    def __init__(self, dbstring: str) -> None:
        logging.info(f'Connecting to database.')
        self.client: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(
            dbstring)
        logging.info(f'Connected to database.')

        self.database: motor.motor_asyncio.AsyncIOMotorDatabase = self.client.data

    @property
    def activeguardsettings(self) -> Collection:
        return Collection(self.database.active_guard_settings)

    @property
    def ai_detection(self) -> Collection:
        return Collection(self.database.ai_detection)

    @property
    def automodsettings(self) -> Collection:
        return Collection(self.database.automodsettings)

    @property
    def currency(self) -> Collection:
        return Collection(self.database.currency)

    @property
    def reports(self) -> Collection:
        return Collection(self.database.reports)

    @property
    def scammer_list(self) -> Collection:
        return Collection(self.database.scammer_list)

    @property
    def serverbans(self) -> Collection:
        return Collection(self.database.serverbans)

    @property
    def autorole_settings(self) -> Collection:
        return Collection(self.database.autorole_settings)

    @property
    def exceptions(self) -> Collection:
        return Collection(self.database.exceptions)

    @property
    def invite_tracking(self) -> Collection:
        return Collection(self.database.invite_tracking, Schemas.InviteTracking)
