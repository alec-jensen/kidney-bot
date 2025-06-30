# Bot class
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import discord
from discord.ext import commands
import asyncio
import logging
from typing import Optional

from utils.config import Config
from utils.database import Database, Schemas, CurrencyDocument, AutoModSettingsDocument
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
        doc = await self.database.currency.find_one({"userID": str(user.id)})
        if doc is not None:
            if location == 'wallet':
                # Handle both schema and dict access patterns
                if isinstance(doc, dict):
                    current_wallet = doc.get('wallet', '0')
                else:
                    current_wallet = getattr(doc, 'wallet', '0')
                wallet_value = int(current_wallet or '0') + value
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'wallet': str(wallet_value)}})
            elif location == 'bank':
                # Handle both schema and dict access patterns  
                if isinstance(doc, dict):
                    current_bank = doc.get('bank', '0')
                else:
                    current_bank = getattr(doc, 'bank', '0')
                bank_value = int(current_bank or '0') + value
                await self.database.currency.update_one({'userID': str(user.id)},
                                                        {'$set': {'bank': str(bank_value)}})
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
        
        # Handle both schema and dict access patterns
        if isinstance(doc, dict):
            log_channel_id = doc.get('log_channel')
        else:
            log_channel_id = getattr(doc, 'log_channel', None)
            
        if log_channel_id is None:
            return

        color = discord.Color.red() if color is None else color

        embed = discord.Embed(title=f'{actiontype}',
                              description=f'{action}\n**User:** {user.mention} ({user.id})\n' +
                              (f"**Target:** {target.mention} ({target.id})" if target is not None else "") +
                              (f"\n**Reason:** {reason}\n" if reason is not None else "") +
                              (f'**Message:** ```{message.content}```' if message is not None else ''),
                              color=color)
        embed.set_footer(text=f'Automated logging by kidney bot')
        
        channel = self.get_channel(log_channel_id)
        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await channel.send(embed=embed)
        return None
    
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
        
        # Handle potential None instance
        bot_instance = KidneyBot.instance
        if bot_instance is None:
            raise RuntimeError("KidneyBot instance not initialized")
        self.bot: KidneyBot = bot_instance

        self.economy = asyncio.create_task(self._optimistic_economy())
        self.scammer_list = asyncio.create_task(
            self._optimistic_scammer_list())

    def require(self, *args):
        """Tell object what data to load. This is a coroutine.
        If this is not called, the object will load all data."""
        if self._optimistic_economy not in args:
            if self.economy is not None:
                if self.economy.done():
                    self.economy = None
                else:
                    self.economy.cancel()
                    self.economy = None

        if self._optimistic_scammer_list not in args:
            if self.scammer_list is not None:
                if self.scammer_list.done():
                    self.scammer_list = None
                else:
                    self.scammer_list.cancel()
                    self.scammer_list = None

    async def _optimistic_economy(self):
        result = await self.bot.database.currency.find_one({"userID": str(self._user.id)})
        return result

    async def _optimistic_scammer_list(self):
        result = await self.bot.database.scammer_list.find_one({"user": str(self._user.id)})
        return result


class KBUser(_OptimisticUser):
    def __init__(self, ctx: Optional[commands.Context] = None, user: Optional[discord.User] = None):
        raise NotImplementedError("KBUser is not implemented yet.")


class KBMember(_OptimisticUser):
    async def async_init(self, ctx: commands.Context, member_input: discord.Member | str):
        if isinstance(member_input, str):
            self.member = await commands.MemberConverter().convert(ctx, member_input)
        elif isinstance(member_input, discord.Member):
            self.member = member_input
        else:
            raise TypeError(
                f"Expected str or discord.Member, got {type(member_input)}")

        _OptimisticUser.__init__(self, self.member)

    def __init__(self, ctx: Optional[commands.Context] = None, member: Optional[discord.Member] = None):
        self.ctx = ctx

        if member is None:
            self.member = None
            return

    async def convert(self, ctx, arg):
        cls = KBMember(ctx=ctx, member=arg)
        await cls.async_init(ctx, arg)
        return cls
