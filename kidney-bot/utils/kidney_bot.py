# Bot class
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional

from utils.config import Config
from utils.database import Database, Schemas
import utils.types as types

def get_prefix(bot: 'KidneyBot', message: discord.Message) -> list[str]:
    return commands.when_mentioned_or(bot.config.prefix)(bot, message)


class KidneyBot(commands.Bot):
    """The main bot class. This is a subclass of commands.Bot, and is used to
    store the database connection, config, and other useful things."""

    instance: 'KidneyBot | None' = None

    def __init__(self, intents):
        self.config: Config = Config()
        super().__init__(
            command_prefix=get_prefix,
            owner_id=self.config.owner_id,
            intents=intents
        )
        KidneyBot.instance = self

        self.database: Database = Database(self.config.dbstring)

    async def setup_hook(self):
        await self.tree.sync()

        # Import is here to prevent circular imports
        from cogs import active_guard
        
        self.add_view(active_guard.ReportView())

    """Add currency to a user's wallet or bank."""
    async def add_currency(self, user: types.AnyUser, value: int, location: str) -> None:
        doc: Schemas.Currency = await self.database.currency.find_one({"userID": str(user.id)}, Schemas.Currency)
        if doc is not None:
            if location == 'wallet':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'wallet': str(int(doc.wallet) + value)}})
            elif location == 'bank':
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'bank': str(int(doc.bank) + value)}})
        else:
            wallet, bank = (0, 0)
            if location == 'wallet':
                wallet = value
            elif location == 'bank':
                bank = value

            document: Schemas.Currency = Schemas.Currency(
                userID=str(user.id),
                wallet=str(wallet),
                bank=str(bank)
            )

            await self.database.currency.insert_one(document)

    """Log an action to the configured log channel for a guild."""
    async def log(self, guild: discord.Guild, actiontype: str, action: str, reason: str, user: types.AnyUser,
                  target: Optional[types.AnyUser] = None, message: Optional[discord.Message] = None,
                  color: Optional[discord.Color] = None) -> Optional[discord.Message]:
        doc = await self.database.automodsettings.find_one({'guild': guild.id})
        if doc is None:
            return
        if doc.get('log_channel') is None:
            return

        color = discord.Color.red() if color is None else color

        embed = discord.Embed(title=f'{actiontype}',
                              description=f'{action}\n**User:** {user.mention} ({user.id})\n' +
                              (f"**Target:** {target.mention} ({target.id})" if target is not None else "") +
                              (f"\n**Reason:** {reason}\n" if reason is not None else "") +
                              (f'**Message:** ```{message.content}```' if message is not None else ''),
                              color=color)
        embed.set_footer(text=f'Automated logging by kidney bot')
        return await self.get_channel(doc['log_channel']).send(embed=embed)
    
    def get_lang_string(self, path: list[str] | str, default: str | None = None) -> str:
        """Get a string from the language file."""

        if type(path) == str:
            path = path.split('.')

        key = self.config.lang
        for arg in path:
            key = key.get(arg)
            if key is None:
                if default is None:
                    raise KeyError(f'Language file is missing key {arg}')
                
                return default
            
        return key


class _OptimisticUser:
    def __init__(self, user: discord.User | discord.Member):
        self._user = user
        logging.info(type(self._user))
        self.bot: KidneyBot = KidneyBot.instance

        self.economy = asyncio.create_task(self._optimistic_economy())
        self.scammer_list = asyncio.create_task(
            self._optimistic_scammer_list())

    def require(self, *args: list[callable]):
        """Tell object what data to load. This is a coroutine.
        If this is not called, the object will load all data."""
        if not self._optimistic_economy in args:
            if self.economy.done():
                self.economy = None
            else:
                self.economy.cancel()
                self.economy = None

        if not self._optimistic_scammer_list in args:
            if self.scammer_list.done():
                self.scammer_list = None
            else:
                self.scammer_list.cancel()
                self.scammer_list = None

    async def _optimistic_economy(self) -> Schemas.Currency:
        return await self.bot.database.currency.find_one({"userID": str(self._user.id)}, Schemas.Currency)

    async def _optimistic_scammer_list(self) -> Schemas.ScammerList:
        return await self.bot.database.scammer_list.find_one({"user": str(self._user.id)}, Schemas.ScammerList)


class KBUser(_OptimisticUser):
    def __init__(self, ctx: commands.Context = None, user: discord.User = None):
        raise NotImplementedError("KBUser is not implemented yet.")


class KBMember(_OptimisticUser):
    async def async_init(self, ctx: commands.Context, member: discord.Member):
        if isinstance(member, str):
            self.member: discord.Member = await commands.MemberConverter().convert(ctx, member)
        elif isinstance(member, discord.Member):
            self.member: discord.Member = member
        else:
            raise TypeError(
                f"Expected str or discord.Member, got {type(member)}")

        _OptimisticUser.__init__(self, self.member)

    def __init__(self, ctx: commands.Context = None, member: discord.Member = None):
        self.ctx: commands.Context = ctx

        if member is None:
            self.member: discord.Member = None
            return

    async def convert(self, ctx, arg):
        cls = KBMember(ctx=ctx, member=arg)
        await cls.async_init(ctx, arg)
        return cls
