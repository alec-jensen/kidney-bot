# Database wrapper
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import logging
import motor.motor_asyncio

class Collection:
    def __init__(self, collection: motor.motor_asyncio.AsyncIOMotorCollection) -> None:
        self.collection: motor.motor_asyncio.AsyncIOMotorCollection = collection

    async def find_one(self, query: dict) -> dict:
        return await self.collection.find_one(query)
    
    async def find(self, query: dict) -> list[dict]:
        return await self.collection.find(query)

    async def update_one(self, query: dict, update: dict) -> None:
        await self.collection.update_one(query, update)

    async def delete_one(self, query: dict) -> None:
        await self.collection.delete_one(query)

    async def insert_one(self, document: dict) -> None:
        await self.collection.insert_one(document)

    async def count_documents(self, query: dict) -> int:
        return await self.collection.count_documents(query)

class Database:
    def __init__(self, dbstring: str) -> None:
        self.client: motor.motor_asyncio.AsyncIOMotorClient = motor.motor_asyncio.AsyncIOMotorClient(dbstring)
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
