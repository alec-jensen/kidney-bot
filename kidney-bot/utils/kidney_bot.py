# Bot class
# Copyright (C) 2023  Alec Jensen
# Full license at LICENSE.md

import asyncio
import logging

import discord
from discord.ext import commands

import utils.types as types
from utils.config import Config
from utils.database import Database, Schemas


def get_prefix(bot: 'KidneyBot', message: discord.Message) -> list[str]:
    return commands.when_mentioned_or(bot.config.prefix)(bot, message)


class KidneyBot(commands.Bot):
    """The main bot class. Stores the database connection, config, and other utilities."""

    instance: 'KidneyBot | None' = None

    def __init__(self, intents: discord.Intents):
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


    async def add_currency(self, user: types.AnyUser, value: int, location: str) -> None:
        """Add currency to a user's wallet or bank."""
        doc = await self.database.currency.get(str(user.id))
        if doc is not None:
            if location == 'wallet':
                doc.wallet = (doc.wallet or 0) + value
            elif location == 'bank':
                doc.bank = (doc.bank or 0) + value
            await self.database.currency.save(doc)
        else:
            wallet, bank = (0, 0)
            if location == 'wallet':
                wallet = value
            elif location == 'bank':
                bank = value
            await self.database.currency.save(Schemas.Currency(
                user_id=str(user.id), wallet=wallet, bank=bank))

    async def log(self, guild: discord.Guild, actiontype: str, action: str, reason: str | None, user: types.AnyUser,
                  target: types.AnyUser | None = None, message: discord.Message | None = None,
                  color: discord.Color | None = None) -> discord.Message | None:
        """Log an action to the configured log channel for a guild."""
        doc = await self.database.automodsettings.get(guild.id)
        if doc is None or doc.log_channel is None:
            return None

        color = discord.Color.red() if color is None else color

        embed = discord.Embed(
            title=f'{actiontype}',
            description=f'{action}\n**User:** {user.mention} ({user.id})\n' +
            (f"**Target:** {target.mention} ({target.id})" if target is not None else "") +
            (f"\n**Reason:** {reason}\n" if reason is not None else "") +
            (f'**Message:** ```{message.content}```' if message is not None else ''),
            color=color)
        embed.set_footer(text='Automated logging by kidney bot')

        channel = self.get_channel(doc.log_channel)
        if channel and isinstance(channel, (discord.TextChannel, discord.Thread)):
            return await channel.send(embed=embed)
        return None

    def get_lang_string(self, path: list[str] | str, default: str | None = None, **kwargs: str) -> str:
        """Get a string from the language file, substituting any {key} placeholders with kwargs."""
        if isinstance(path, str):
            path = path.split('.')

        key = self.config.lang
        for arg in path:
            key = key.get(arg)
            if key is None:
                if default is None:
                    raise KeyError(f'Language file is missing key {arg}')
                return default

        if kwargs:
            return key.format_map(kwargs)
        return key


class _OptimisticUser:
    def __init__(self, user: discord.User | discord.Member):
        self._user = user
        logging.info(type(self._user))

        bot_instance = KidneyBot.instance
        if bot_instance is None:
            raise RuntimeError("KidneyBot instance not initialized")
        self.bot: KidneyBot = bot_instance

        self.economy = asyncio.create_task(self._optimistic_economy())
        self.scammer_list = asyncio.create_task(self._optimistic_scammer_list())

    def require(self, *args: object) -> None:
        """Tell object what data to load. If not called, all data is loaded."""
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
        return await self.bot.database.currency.get(str(self._user.id))

    async def _optimistic_scammer_list(self):
        return await self.bot.database.scammer_list.get(str(self._user.id))


class KBUser(_OptimisticUser):
    def __init__(self, ctx: commands.Context | None = None, user: discord.User | None = None):
        raise NotImplementedError("KBUser is not implemented yet.")


class KBMember(_OptimisticUser):
    async def async_init(self, ctx: commands.Context, member_input: discord.Member | str):
        if isinstance(member_input, str):
            self.member = await commands.MemberConverter().convert(ctx, member_input)
        else:
            self.member = member_input

        _OptimisticUser.__init__(self, self.member)

    def __init__(self, ctx: commands.Context | None = None, member: discord.Member | None = None):
        self.ctx = ctx

        if member is None:
            self.member = None
            return

    async def convert(self, ctx: commands.Context, arg: discord.Member | str):
        cls = KBMember(ctx=ctx)
        await cls.async_init(ctx, arg)
        return cls
